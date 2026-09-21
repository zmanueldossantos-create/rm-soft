"""End to end: a receipt created for an invoice with withholding is exported in Payments, tied to that invoice's InvoiceNo."""
import pytest
from lxml import etree

from app.models.customer import Customer, LegalPersonType
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import create_invoice, create_receipt
from app.services.saf_t_export_service import export_saf_t_for_period

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


@pytest.mark.asyncio
async def test_receipt_is_exported_in_payments_with_its_invoice_and_withholding(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    tax = WithholdingTax(name="Retencao export", rate=6.5, tax_type="II")
    db.add(tax)
    customer = Customer(company_id=company_id, name="Empresa PJ", nif="5000111777", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(tax)
    await db.refresh(customer)
    customer_id = customer.id
    service = Service(company_id=company_id, code="SRV-EXP", name="Servico export", price=1000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    invoice = await create_invoice(  # 2280, withholding 130, cash due 2150
        db, company_id, activity_id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id, year, month = invoice.id, invoice.business_date.year, invoice.business_date.month
    await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=2150.0)

    root = etree.fromstring(await export_saf_t_for_period(db, company_id, year, month))
    invoice_no = root.findtext(".//s:SalesInvoices/s:Invoice/s:InvoiceNo", namespaces=NS)
    payment = root.find(".//s:Payments/s:Payment", NS)
    assert payment.findtext("s:Line/s:SourceDocumentID/s:OriginatingON", namespaces=NS) == invoice_no
    assert payment.findtext("s:PaymentMethod/s:PaymentMechanism", namespaces=NS) == "NU"
    assert payment.findtext("s:PaymentMethod/s:PaymentAmount", namespaces=NS) == "2150.00"
    assert payment.findtext("s:Line/s:CreditAmount", namespaces=NS) == "2000.00"
    assert [payment.findtext("s:DocumentTotals/s:" + k, namespaces=NS) for k in ("TaxPayable", "NetTotal", "GrossTotal")] == ["280.00", "2000.00", "2280.00"]
    tax_el = payment.find("s:WithholdingTax", NS)
    assert (tax_el.findtext("s:WithholdingTaxType", namespaces=NS), tax_el.findtext("s:WithholdingTaxAmount", namespaces=NS)) == ("II", "130.00")
    assert root.findtext(".//s:SalesInvoices/s:NumberOfEntries", namespaces=NS) == "1"