"""
The type of the withholding (SAF-T WithholdingTaxType) is copied from the catalog onto the invoice line, and a credit
note copies it from the line it credits. A catalog entry without a type leaves it empty (reported as "OU").
"""
import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.services.invoice_service import create_credit_note, create_invoice


async def _line(db, invoice_id):
    return (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()


async def _issue(db, ctx, customer_id, code, tax):
    service = Service(company_id=ctx["company"].id, code=code, name="Servico " + code, price=1000.0,
                      vat_id=ctx["vat_nor"].id, withholding_tax_id=tax.id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id
    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=customer_id, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    return invoice.id


@pytest.mark.asyncio
async def test_retention_type_is_copied_on_the_line_and_on_its_credit_note(db, company_with_essentials):
    ctx = company_with_essentials
    typed = WithholdingTax(name="Retencao com tipo", rate=6.5, tax_type="II")
    untyped = WithholdingTax(name="Retencao sem tipo", rate=5)
    db.add_all([typed, untyped])
    customer = Customer(company_id=ctx["company"].id, name="Empresa PJ", nif="5000111444", legal_person_type=LegalPersonType.JURIDICA)
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    await db.refresh(typed)
    await db.refresh(untyped)
    customer_id = customer.id

    typed_invoice_id = await _issue(db, ctx, customer_id, "SRV-T", typed)
    line = await _line(db, typed_invoice_id)
    assert line.retention_type == "II" and float(line.retention_amount) == 130.0
    line_id = line.id

    credit_note = await create_credit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=typed_invoice_id,
        credit_note_reason="RTF", credit_note_cause="Correcao de teste",
        lines_input=[{"invoice_line_id": line_id, "quantity": 1}],
    )
    credit_note_id = credit_note.id
    assert (await _line(db, credit_note_id)).retention_type == "II"

    untyped_line = await _line(db, await _issue(db, ctx, customer_id, "SRV-U", untyped))
    assert untyped_line.retention_type is None and float(untyped_line.retention_amount) == 100.0