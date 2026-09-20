"""
A credit note follows the invoice it credits: the amount keeps the original line discount (it used to be re-priced
as quantity x unit_price, crediting more than invoiced) and the withholding is carried pro rata, from the snapshot
kept on the original line.
"""
import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import create_credit_note, create_invoice


async def _service(db, ctx, code, withholding_tax_id=None):
    service = Service(
        company_id=ctx["company"].id, code=code, name="Servico " + code, price=1000.0,
        vat_id=ctx["vat_nor"].id, withholding_tax_id=withholding_tax_id,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service.id


async def _credit(db, ctx, invoice_id, quantity):
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    line_id = line.id
    return await create_credit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id,
        credit_note_reason="RTF", credit_note_cause="Correcao de teste",
        lines_input=[{"invoice_line_id": line_id, "quantity": quantity}],
    )


@pytest.mark.asyncio
async def test_credit_note_carries_the_withholding_pro_rata(db, company_with_essentials):
    ctx = company_with_essentials
    tax = WithholdingTax(name="Retencao teste", rate=6.5)
    db.add(tax)
    await db.flush()
    service_id = await _service(db, ctx, "SRV-RN", withholding_tax_id=tax.id)
    customer = Customer(company_id=ctx["company"].id, name="Empresa PJ", nif="5000111333", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    customer_id = customer.id

    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id = invoice.id
    assert float(invoice.retention_total) == 130.0

    credit_note = await _credit(db, ctx, invoice_id, 1)  # one unit of two
    credit_note_id = credit_note.id
    assert float(credit_note.total) == 1140.0
    assert float(credit_note.retention_total) == 65.0
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == credit_note_id))).scalars().one()
    assert line.retention_name_snapshot == "Retencao teste"
    assert float(line.retention_rate) == 6.5 and float(line.retention_amount) == 65.0


@pytest.mark.asyncio
async def test_credit_note_without_retention_keeps_it_empty(db, company_with_essentials):
    ctx = company_with_essentials
    service_id = await _service(db, ctx, "SRV-SR")
    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 1}],
    )
    invoice_id = invoice.id
    credit_note = await _credit(db, ctx, invoice_id, 1)
    credit_note_id = credit_note.id
    assert float(credit_note.retention_total) == 0.0
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == credit_note_id))).scalars().one()
    assert line.retention_rate is None and line.retention_amount is None


@pytest.mark.asyncio
async def test_credit_note_keeps_the_line_discount_of_the_original(db, company_with_essentials):
    ctx = company_with_essentials
    service_id = await _service(db, ctx, "SRV-DC")
    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2, "discount_percent": 10}],
    )
    invoice_id = invoice.id
    assert float(invoice.subtotal) == 1800.0 and float(invoice.total) == 2052.0

    credit_note = await _credit(db, ctx, invoice_id, 2)  # the whole invoice: used to be refused (2280 > 2052)
    credit_note_id = credit_note.id
    assert float(credit_note.subtotal) == 1800.0 and float(credit_note.total) == 2052.0
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == credit_note_id))).scalars().one()
    assert float(line.discount_percent) == 10.0