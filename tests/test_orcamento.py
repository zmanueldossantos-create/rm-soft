"""Point 2: the Orçamento (OR) - a quote to a customer with a validity date, a working document like the pro-forma
(SAF-T WorkingDocuments, WorkType OR); converted into an invoice while valid, at the prices announced - the pro-forma
keeps its prices too."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest
from lxml import etree
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.invoice_service import (
    EmptyInvoiceError, QuoteExpiredError, convert_pro_forma_to_invoice, create_pro_forma,
)
from app.services.saf_t_export_service import export_saf_t_for_period
from app.utils.pdf_generator import _reference_texts

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


async def _setup(db, ctx, code):
    company_id = ctx["company"].id
    service = Service(company_id=company_id, code=code, name="Catering", price=10000.0, vat_id=ctx["vat_nor"].id)
    customer = Customer(company_id=company_id, name="Hotel Kilamba", nif="5000" + code[-6:].replace("-", "0").rjust(6, "1"),
                        legal_person_type=LegalPersonType.JURIDICA)
    db.add_all([service, customer])
    await db.commit()
    return company_id, ctx["activity"].id, service.id, customer.id


@pytest.mark.asyncio
async def test_an_orcamento_is_converted_at_its_prices_while_valid(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, service_id, customer_id = await _setup(db, ctx, "SRV-OR1")
    lines = [{"service_id": service_id, "quantity": 2}]
    with pytest.raises(EmptyInvoiceError, match="cliente"):
        await create_pro_forma(db, company_id, activity_id, None, lines, invoice_type="ORCAMENTO")
    with pytest.raises(EmptyInvoiceError, match="validade"):
        await create_pro_forma(db, company_id, activity_id, customer_id, lines, invoice_type="ORCAMENTO",
                               valid_until=date.today() - timedelta(days=1))

    quote = await create_pro_forma(db, company_id, activity_id, customer_id, lines, invoice_type="ORCAMENTO")
    quote_id, quote_ref = quote.id, f"OR {quote.series}/{quote.number}"
    assert quote.invoice_type == InvoiceType.ORCAMENTO and quote.valid_until == date.today() + timedelta(days=30)
    assert float(quote.subtotal) == 20000.0

    service = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one()
    service.price = 12000.0  # the price changes after the quote
    await db.commit()

    invoice = await convert_pro_forma_to_invoice(db, company_id, quote_id, "FACTURA")
    invoice_id = invoice.id
    assert invoice.document_reference == quote_ref
    assert float(invoice.subtotal) == 20000.0  # the price announced, not today's
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalar_one()
    assert float(line.unit_price) == 10000.0
    quote = (await db.execute(select(Invoice).where(Invoice.id == quote_id))).scalar_one()
    assert quote.converted_to_invoice_id == invoice_id

    # an expired orçamento is not converted
    expired = await create_pro_forma(db, company_id, activity_id, customer_id, lines, invoice_type="ORCAMENTO")
    expired.valid_until = date.today() - timedelta(days=1)
    await db.commit()
    with pytest.raises(QuoteExpiredError, match="expirou"):
        await convert_pro_forma_to_invoice(db, company_id, expired.id, "FACTURA")

    # the SAF-T: the orçamento among the working documents (OR, invoiced F), the invoice naming it
    today = datetime.now().date()
    root = etree.fromstring(await export_saf_t_for_period(db, company_id, today.year, today.month))
    etree.XMLSchema(etree.parse(str(Path(__file__).parent / "data" / "SAFTAO1.01_01.xsd"))).assertValid(root)
    works = {d.findtext("s:DocumentNumber", namespaces=NS): d for d in root.findall(".//s:WorkingDocuments/s:WorkDocument", NS)}
    assert works[quote_ref].findtext("s:WorkType", namespaces=NS) == "OR"
    assert works[quote_ref].findtext("s:DocumentStatus/s:WorkStatus", namespaces=NS) == "F"
    origins = [i.findtext("s:Line/s:OrderReferences/s:OriginatingON", namespaces=NS)
               for i in root.findall(".//s:SalesInvoices/s:Invoice", NS)]
    assert quote_ref in origins


@pytest.mark.asyncio
async def test_a_pro_forma_keeps_its_prices_too(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, service_id, _ = await _setup(db, ctx, "SRV-OR2")
    pro_forma = await create_pro_forma(db, company_id, activity_id, None, [{"service_id": service_id, "quantity": 1}])
    pro_forma_id = pro_forma.id
    assert pro_forma.valid_until is None
    service = (await db.execute(select(Service).where(Service.id == service_id))).scalar_one()
    service.price = 15000.0
    await db.commit()
    invoice = await convert_pro_forma_to_invoice(db, company_id, pro_forma_id, "FACTURA")
    assert float(invoice.subtotal) == 10000.0


def test_the_printed_orcamento_shows_its_validity_and_is_not_an_invoice():
    assert _reference_texts({"invoice_type": "OR", "valid_until": date(2026, 11, 14)}) == [
        "Válido até: 14/11/2026", "Este documento não serve de fatura"]
    assert _reference_texts({"invoice_type": "FP"}) == ["Este documento não serve de fatura"]
    assert _reference_texts({"invoice_type": "FT"}) == []
