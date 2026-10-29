"""
A document as the AGT's Faturação Eletrónica receives it (registarFactura, Schema 2.0): built from the invoice, its
lines and its customer, signed with the issuer's key (jwsDocumentSignature over documentNo, taxRegistrationNumber,
documentType, documentDate, customerTaxID, customerCountry, companyName, documentTotals).

The rules followed (AGT, «Registar Factura»):
- documentNo = «<type> <series>/<number>», as in the SAF-T (FT FT26SEDEN/12);
- a customer without a NIF: customerTaxID «999999999», country AO; companyName is the customer's name;
- lines numbered 1, 2, 3... (E12), operationType TB for goods, SHS for the services of a hotel / restaurant / bar, SS
  health, SE education, SG the other services; unitPriceBase the price before discounts, unitPrice after them,
  creditAmount (a sale) / debitAmount (a credit note) the line net of tax, settlementAmount the discounts;
- taxes: IVA with its code (NOR, INT, RED, ISE, OUT) and percentage, taxContribution rounded UP to the next cent, the
  exemption code when ISE; IEC / IS when the line carries them;
- the totals are the sums of the lines (E22-E24): the document's global discount is spread on its lines;
- a credit / debit note carries the invoice it corrects (referenceInfo); a receipt has no lines but the documents it
  pays (paymentReceipt); the withholdings go in withholdingTaxList.
"""
import math
from datetime import timezone
from decimal import ROUND_HALF_UP, Decimal
from urllib.parse import quote

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.country import Country
from app.models.customer import Customer
from app.models.document_type import DocumentType
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.module import Module
from app.models.product import Product
from app.models.service import Service
from app.services import agt_signing

ANONYMOUS_NIF = "999999999"
# The QR's address: {documento} the document (FR FR26S1N/226, encoded), {nif} the issuer's NIF. The default is the one
# printed by the certified programs today (portal do contribuinte); the AGT's specification gave
# https://quiosqueagt.minfin.gov.ao/facturacao-eletronica/consultar-fe?emissor={nif}&document={documento} - the
# SUPER_ADMIN changes it in Configurações → Faturação Eletrónica, without a new version.
QR_URL_DEFAULT = "https://portaldocontribuinte.minfin.gov.ao/consultar-fe?{documento}"
SERVICE_OPERATION = {"HOTEL": "SHS", "RESTAURANTE": "SHS", "BAR": "SHS", "HOSPITAL": "SS", "ESCOLA": "SE"}
TYPE_CODE = {"FACTURA": "FT", "FACTURA_RECIBO": "FR", "NOTA_CREDITO": "NC", "NOTA_DEBITO": "ND", "RECIBO": "RC",
             "PRO_FORMA": "FP", "ORCAMENTO": "OR"}
NO_LINES = {"RC", "AR", "RG"}  # documents with paymentReceipt instead of lines


def money(value) -> float:
    return float(Decimal(str(value or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def tax_up(value) -> float:
    """taxContribution: rounded UP to the next cent (23,144 → 23,15 ; 5,9999999 → 6,00)."""
    cents = Decimal(str(value or 0)) * 100
    return float(Decimal(math.ceil(cents.quantize(Decimal("0.000001")))) / 100)


async def type_code(db: AsyncSession, invoice: Invoice) -> str:
    if invoice.document_type_id is not None:
        doc_type = await db.get(DocumentType, invoice.document_type_id)
        if doc_type is not None:
            return doc_type.code
    kind = invoice.invoice_type.value if hasattr(invoice.invoice_type, "value") else str(invoice.invoice_type)
    return TYPE_CODE.get(kind, kind)


def document_no(code: str, invoice: Invoice) -> str:
    return f"{code} {invoice.series}/{invoice.number}"


def qr_url(issuer_nif: str, number: str, template: str | None = None) -> str:
    """The QR code printed on an electronic document: the AGT's page of the document (FR FR26S1N/226 →
    FR%20FR26S1N%2F226)."""
    return (template or QR_URL_DEFAULT).replace("{nif}", quote(issuer_nif.strip(), safe="")).replace(
        "{documento}", quote(number, safe=""))


def _when(moment) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


async def _customer(db: AsyncSession, invoice: Invoice) -> tuple[str, str, str]:
    """(customerTaxID, customerCountry, companyName)."""
    customer = await db.get(Customer, invoice.customer_id) if invoice.customer_id else None
    if customer is None:
        return ANONYMOUS_NIF, "AO", "Consumidor final"
    country = "AO"
    if customer.country_id is not None:
        row = await db.get(Country, customer.country_id)
        if row is not None and len(row.code or "") == 2:
            country = row.code.upper()
    nif = (customer.nif or "").strip()
    if customer.is_final_consumer or not nif:
        nif = ANONYMOUS_NIF
    return nif, country, (customer.fiscal_name or customer.name or "Consumidor final")[:200]


async def _operation(db: AsyncSession, invoice: Invoice) -> str:
    activity = await db.get(Activity, invoice.activity_id) if invoice.activity_id else None
    module = await db.get(Module, activity.module_id) if activity is not None else None
    return SERVICE_OPERATION.get((module.code or "") if module is not None else "", "SG")


async def _lines(db: AsyncSession, invoice: Invoice, credit_note: bool) -> list[dict]:
    rows = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id)
                             .order_by(InvoiceLine.line_number, InvoiceLine.created_at, InvoiceLine.id))).scalars().all()
    service_operation = await _operation(db, invoice)
    keep = 1 - float(invoice.discount_global_percent or 0) / 100  # the global discount, spread on the lines
    out = []
    for number, line in enumerate(rows, start=1):
        if line.product_id is not None:
            item = await db.get(Product, line.product_id)
            operation = "TB"
        else:
            item = await db.get(Service, line.service_id) if line.service_id else None
            operation = service_operation
        quantity = float(line.quantity)
        base = money(line.unit_price)
        net = money(float(line.line_subtotal) * keep)
        vat = float(line.line_vat) * keep
        tax = {"taxType": "IVA", "taxCountryRegion": "AO", "taxCode": line.tax_code_snapshot or "NOR",
               "taxPercentage": float(line.vat_rate_snapshot or 0), "taxContribution": tax_up(vat)}
        if (line.tax_code_snapshot or "") == "ISE" or float(line.vat_rate_snapshot or 0) == 0:
            tax["taxCode"] = "ISE"
            if line.exemption_code:
                tax["taxExemptionCode"] = line.exemption_code
        taxes = [tax]
        if float(line.iec_amount or 0) > 0:
            taxes.append({"taxType": "IEC", "taxCountryRegion": "AO", "taxContribution": tax_up(line.iec_amount)})
        if float(line.iselo_amount or 0) > 0:
            taxes.append({"taxType": "IS", "taxCountryRegion": "AO", "taxContribution": tax_up(line.iselo_amount)})
        entry = {
            "lineNumber": number,
            "operationType": operation,
            "productCode": ((item.code if item is not None else None) or "ART")[:60],
            "productDescription": (line.product_name_snapshot or "Artigo")[:200],
            "quantity": quantity,
            "unitOfMeasure": (line.unit_code_snapshot or "UN")[:20],
            "unitPriceBase": base,
            "unitPrice": money(net / quantity) if quantity else base,
            ("debitAmount" if credit_note else "creditAmount"): net,
            "taxes": taxes,
            "settlementAmount": money(max(base * quantity - net, 0)),
        }
        out.append(entry)
    return out


def _totals(lines: list[dict]) -> dict:
    net = money(sum(l.get("creditAmount", l.get("debitAmount", 0)) for l in lines))
    tax = money(sum(t["taxContribution"] for l in lines for t in l["taxes"]))
    return {"taxPayable": tax, "netTotal": net, "grossTotal": money(net + tax)}


async def _withholdings(db: AsyncSession, invoice: Invoice) -> list[dict]:
    rows = (await db.execute(select(InvoiceLine.retention_type, InvoiceLine.retention_name_snapshot,
                                    InvoiceLine.retention_amount).where(
        InvoiceLine.invoice_id == invoice.id, InvoiceLine.retention_amount.is_not(None)))).all()
    grouped: dict[str, dict] = {}
    for kind, name, amount in rows:
        key = (kind or "OU")[:3]
        entry = grouped.setdefault(key, {"withholdingTaxType": key, "withholdingTaxDescription": (name or "")[:120],
                                         "withholdingTaxAmount": 0.0})
        entry["withholdingTaxAmount"] = money(entry["withholdingTaxAmount"] + float(amount or 0))
    return list(grouped.values())


async def build_document(db: AsyncSession, invoice: Invoice, issuer_nif: str, private_key: str,
                         rejected_document_no: str | None = None) -> dict:
    """The document of registarFactura, signed. rejected_document_no: a correction (documentStatus C) of a document
    the AGT refused."""
    code = await type_code(db, invoice)
    number = document_no(code, invoice)
    customer_nif, country, name = await _customer(db, invoice)
    document = {
        "documentNo": number,
        "documentStatus": "C" if rejected_document_no else "N",
    }
    if rejected_document_no:
        document["rejectedDocumentNo"] = rejected_document_no
    document.update({
        "documentDate": invoice.business_date.isoformat(),
        "documentType": code,
        "systemEntryDate": _when(invoice.created_at),
        "customerTaxID": customer_nif,
        "customerCountry": country,
        "companyName": name,
    })
    reference = await db.get(Invoice, invoice.reference_invoice_id) if invoice.reference_invoice_id else None
    if code in NO_LINES:
        source = []
        if reference is not None:
            source.append({"lineNo": 1, "sourceDocumentID": {
                "OriginatingON": document_no(await type_code(db, reference), reference),
                "documentDate": reference.business_date.isoformat()}, "creditAmount": money(invoice.subtotal)})
        document["paymentReceipt"] = {"sourceDocuments": source}
        totals = {"taxPayable": money(invoice.vat_total), "netTotal": money(invoice.subtotal),
                  "grossTotal": money(float(invoice.subtotal) + float(invoice.vat_total))}
    else:
        lines = await _lines(db, invoice, credit_note=(code == "NC"))
        if reference is not None and code in ("NC", "ND"):
            info = {"reference": document_no(await type_code(db, reference), reference)}
            if invoice.credit_note_cause:
                info["reason"] = invoice.credit_note_cause[:60]
            for line in lines:
                line["referenceInfo"] = info
        document["lines"] = lines
        totals = _totals(lines)
    document["documentTotals"] = totals
    withholdings = await _withholdings(db, invoice)
    if withholdings:
        document["withholdingTaxList"] = withholdings
    signed = {"documentNo": number, "taxRegistrationNumber": issuer_nif, "documentType": code,
              "documentDate": document["documentDate"], "customerTaxID": customer_nif, "customerCountry": country,
              "companyName": name, "documentTotals": totals}
    document["jwsDocumentSignature"] = agt_signing.sign(signed, private_key)
    return document
