"""
SAF-T export service - gathers a company's data for a given fiscal period
(year/month) and generates the AuditFile XML. See specification v6/v7,
section 4.2 "Modo Fatura" - exported at month end, submitted manually to
the AGT portal by the business.
"""
import uuid
from datetime import date
from calendar import monthrange

from sqlalchemy import select, text
from app.models.document_type import DocumentType
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.customer import Customer
from app.models.product import Product
from app.models.service import Service
from app.models.vat import VAT
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.platform_settings import PlatformSettings
from app.utils.saf_t_generator import INVOICE_TYPE_MAP, generate_saf_t_xml


class CompanyNotFoundError(Exception):
    pass


async def _receipt_extras(db: AsyncSession, receipt: Invoice) -> dict:
    """What the SAF-T Payments section needs about a receipt: the invoice it settles (its InvoiceNo and date), the
    cash by payment method, and the withholding - by type - the receipt settles (the settled share of the invoice's)."""
    extras: dict = {"reference_invoice_no": None, "reference_invoice_date": None, "payment_methods": [], "withholding": []}
    ref = None
    if receipt.reference_invoice_id is not None:
        ref = (await db.execute(select(Invoice).where(Invoice.id == receipt.reference_invoice_id))).scalar_one_or_none()
    if ref is not None:
        extras["reference_invoice_no"] = f"{INVOICE_TYPE_MAP.get(ref.invoice_type.value, 'FT')} {ref.series}/{ref.number}"
        extras["reference_invoice_date"] = ref.business_date
    rows = (await db.execute(
        text("SELECT pm.code, p.amount FROM payments p JOIN payment_method_catalog pm ON pm.id = p.payment_method_id WHERE p.invoice_id = :id"),
        {"id": receipt.id},
    )).all()
    extras["payment_methods"] = [{"code": code, "amount": float(amount)} for code, amount in rows]
    if ref is not None and float(receipt.retention_total or 0) > 0 and float(ref.retention_total or 0) > 0:
        share = float(receipt.retention_total) / float(ref.retention_total)
        by_type: dict[str, dict] = {}
        for line in (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == ref.id))).scalars().all():
            if line.retention_amount:
                entry = by_type.setdefault(line.retention_type or "OU", {"amount": 0.0, "name": line.retention_name_snapshot})
                entry["amount"] += float(line.retention_amount)
        withholding = [{"type": k, "name": v["name"], "amount": round(v["amount"] * share, 2)} for k, v in by_type.items()]
        difference = round(float(receipt.retention_total) - sum(w["amount"] for w in withholding), 2)
        if withholding and difference:  # rounding: the entries must add up to the receipt's own withholding
            withholding[0]["amount"] = round(withholding[0]["amount"] + difference, 2)
        extras["withholding"] = withholding
    return extras


async def export_saf_t_for_period(db: AsyncSession, company_id: uuid.UUID, year: int, month: int) -> bytes:
    """Generates the SAF-T AuditFile XML for one calendar month."""
    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError("Empresa nao encontrada")

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    # Stable order: the SAF-T CustomerID is the position in this list, so it must not shift between exports.
    customers_result = await db.execute(
        select(Customer).where(Customer.company_id == company_id).order_by(Customer.created_at, Customer.id)
    )
    customers = customers_result.scalars().all()

    products_result = await db.execute(select(Product).where(Product.company_id == company_id))
    products = products_result.scalars().all()

    # Services are sellable articles too: a service line has no product_id, so it used to be exported with
    # ProductCode "N/A" - which matches no MasterFiles/Product (XSD keyref InvoiceProductCodeConstraint) -
    # and the service itself never reached MasterFiles.
    services_result = await db.execute(select(Service).where(Service.company_id == company_id))
    services = services_result.scalars().all()
    product_code_by_id = {p.id: p.code for p in products}
    service_code_by_id = {s.id: s.code for s in services}

    vat_result = await db.execute(select(VAT).where(VAT.company_id == company_id))
    vat_rates = vat_result.scalars().all()

    invoices_result = await db.execute(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= start_date,
            Invoice.business_date <= end_date,
        )
    )
    invoices = invoices_result.scalars().all()

    settings_result = await db.execute(select(PlatformSettings).limit(1))
    platform_settings = settings_result.scalar_one_or_none()

    # SAF-T section of each document (Faturas / Payments / Working), from the document type catalog.
    section_by_code = {code: section for code, section in (await db.execute(select(DocumentType.code, DocumentType.saft_section))).all()}
    invoices_data = []
    for inv in invoices:
        receipt_extra = await _receipt_extras(db, inv) if inv.invoice_type.value == "RECIBO" else {}
        lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
        lines = lines_result.scalars().all()

        invoices_data.append({
            "invoice_type": inv.invoice_type.value,
            "series": inv.series,
            "number": inv.number,
            "business_date": inv.business_date,
            "created_at": inv.created_at.replace(tzinfo=None),
            "atcud": inv.atcud,
            "invoice_hash": inv.invoice_hash,
            "subtotal": float(inv.subtotal),
            "vat_total": float(inv.vat_total),
            "total": float(inv.total),
            "customer_id": str(inv.customer_id) if inv.customer_id else None,
            "document_reference": inv.document_reference,
            "credit_note_cause": inv.credit_note_cause,
            "converted": inv.converted_to_invoice_id is not None,
            **receipt_extra,
            "saft_section": section_by_code.get(DOC_CODE_BY_INVOICE_TYPE.get(inv.invoice_type.value, ""), "NONE"),
            "lines": [
                {
                    "product_code": product_code_by_id.get(l.product_id) or service_code_by_id.get(l.service_id) or "N/A",
                    "product_name": l.product_name_snapshot,
                    "quantity": float(l.quantity),
                    "unit_price": float(l.unit_price),
                    "vat_rate": float(l.vat_rate_snapshot), "tax_code": l.tax_code_snapshot,
                    "line_subtotal": float(l.line_subtotal),
                    "line_vat": float(l.line_vat),
                    "line_total": float(l.line_total),
                    "exemption_code": l.exemption_code,
                    "retention_type": l.retention_type,
                    "retention_name": l.retention_name_snapshot,
                    "retention_amount": float(l.retention_amount) if l.retention_amount is not None else None,
                }
                for l in lines
            ],
        })

    company_dict = {
        "name": company.name,
        "nif": company.nif,
        "address": company.address,
        "phone_number": company.phone_number,
        "email": company.email,
        "commercial_registration_number": company.commercial_registration_number,
    }
    platform_dict = {
        "software_validation_number": platform_settings.software_validation_number if platform_settings else None,
        "vendor_tax_id": platform_settings.vendor_tax_id if platform_settings else None,
        "product_id": platform_settings.product_id if platform_settings else None,
        "product_version": platform_settings.product_version if platform_settings else None,
    }
    customers_data = [
        {"id": str(c.id), "nif": c.nif, "name": c.name, "address": c.address, "phone_number": c.phone_number, "email": c.email}
        for c in customers
    ]
    products_data = [{"code": p.code, "name": p.name, "product_type": p.product_type.value} for p in products]
    known_codes = {d["code"] for d in products_data}
    products_data += [{"code": s.code, "name": s.name, "product_type": "SERVICO"} for s in services if s.code not in known_codes]
    vat_data = [{"name": v.name, "rate": float(v.rate), "tax_code": v.tax_category} for v in vat_rates]

    return generate_saf_t_xml(
        company=company_dict,
        platform_settings=platform_dict,
        customers=customers_data,
        products=products_data,
        vat_rates=vat_data,
        invoices=invoices_data,
        fiscal_year=year,
        start_date=start_date,
        end_date=end_date,
    )
