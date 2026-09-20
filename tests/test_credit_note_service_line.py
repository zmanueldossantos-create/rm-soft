"""
A credit note copies the lines of the invoice it credits: a service line must keep its service (it used to keep only
product_id, so the line lost the link and the SAF-T export fell back to ProductCode "N/A").
"""
import pytest
from sqlalchemy import select

from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.invoice_service import create_credit_note, create_invoice


@pytest.mark.asyncio
async def test_credit_note_lines_keep_the_service(db, company_with_essentials):
    ctx = company_with_essentials
    service = Service(company_id=ctx["company"].id, code="SRV-NC", name="Servico NC", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id = invoice.id
    original_line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    original_line_id = original_line.id

    credit_note = await create_credit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id,
        credit_note_reason="ANL", credit_note_cause="Cliente desistiu do servico",
        lines_input=[{"invoice_line_id": original_line_id, "quantity": 2}],
    )
    credit_note_id = credit_note.id

    credit_line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == credit_note_id))).scalars().one()
    assert credit_line.service_id == service_id and credit_line.product_id is None