"""
Tests for the retention snapshot on invoice lines: what was withheld (name, rate, amount) is copied onto the
line when the invoice is issued and does not move when the withholding catalog changes later - like
vat_rate_snapshot for the VAT. A line with no retention keeps the three columns empty.
"""
import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.schemas.invoice import InvoiceLineResponse
from app.services.invoice_service import create_invoice


async def _service_with_retention(db, ctx):
    tax = WithholdingTax(name="Retencao teste", rate=6.5)
    db.add(tax)
    await db.flush()
    service = Service(
        company_id=ctx["company"].id, code="SRV-RET", name="Servico com retencao", price=1000.0,
        vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    await db.refresh(tax)
    return service.id, tax.id


async def _only_line(db, invoice_id):
    return (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()


@pytest.mark.asyncio
async def test_line_keeps_the_retention_it_was_issued_with(db, company_with_essentials):
    ctx = company_with_essentials
    service_id, tax_id = await _service_with_retention(db, ctx)
    customer = Customer(company_id=ctx["company"].id, name="Empresa PJ", nif="5000111222", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    customer_id = customer.id

    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id = invoice.id
    assert float(invoice.retention_total) == 130.0  # 6.5% of 2 x 1000

    line = await _only_line(db, invoice_id)
    assert line.retention_name_snapshot == "Retencao teste"
    assert float(line.retention_rate) == 6.5 and float(line.retention_amount) == 130.0

    # The catalog changes later: the issued document must not.
    tax = (await db.execute(select(WithholdingTax).where(WithholdingTax.id == tax_id))).scalar_one()
    tax.rate = 10
    tax.name = "Outra retencao"
    await db.commit()
    line = await _only_line(db, invoice_id)
    await db.refresh(line)
    assert (line.retention_name_snapshot, float(line.retention_rate), float(line.retention_amount)) == ("Retencao teste", 6.5, 130.0)


@pytest.mark.asyncio
async def test_line_without_retention_has_an_empty_snapshot(db, company_with_essentials):
    ctx = company_with_essentials
    service_id, _tax_id = await _service_with_retention(db, ctx)

    invoice = await create_invoice(  # walk-in sale: no customer, so no retention
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    invoice_id = invoice.id
    assert float(invoice.retention_total) == 0.0
    line = await _only_line(db, invoice_id)
    assert line.retention_name_snapshot is None and line.retention_rate is None and line.retention_amount is None


def test_invoice_line_response_exposes_the_retention_snapshot():
    for name in ("retention_name_snapshot", "retention_rate", "retention_amount"):
        assert name in InvoiceLineResponse.model_fields