"""
The exemption motive of an exempt article - its code and official reason, from the catalog - is copied onto every line
issued: invoice, debit note, pro-forma; a credit note copies it from the line it credits. A taxed line has none.
"""
import pytest
from sqlalchemy import select

from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.invoice_service import create_credit_note, create_debit_note, create_invoice, create_pro_forma


async def _motives(db, document_id):
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == document_id))).scalars().all()
    return {l.service_id: (l.exemption_code, l.exemption_reason_snapshot) for l in lines}


@pytest.mark.asyncio
async def test_exemption_motive_is_copied_on_every_document(db, company_with_essentials):
    ctx = company_with_essentials
    m11 = ctx["exemption_m11"]
    motive = (m11.code, m11.name)
    exempt = Service(company_id=ctx["company"].id, code="SRV-EX", name="Servico isento", price=1000.0,
                     vat_id=ctx["vat_ise"].id, exemption_reason_id=m11.id)
    taxed = Service(company_id=ctx["company"].id, code="SRV-TX", name="Servico taxado", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add_all([exempt, taxed])
    await db.commit()
    exempt_id, taxed_id = exempt.id, taxed.id

    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": s, "quantity": 1} for s in (exempt_id, taxed_id)],
    )
    invoice_id = invoice.id
    assert await _motives(db, invoice_id) == {exempt_id: motive, taxed_id: (None, None)}

    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().all()
    line_ids = [l.id for l in lines]
    credit_note = await create_credit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id,
        # RTF, not ANL: a full ANL credit note annuls the invoice, and a debit note on an annulled invoice is refused.
        credit_note_reason="RTF", credit_note_cause="Rectificacao de teste",
        lines_input=[{"invoice_line_id": i, "quantity": 1} for i in line_ids],
    )
    assert await _motives(db, credit_note.id) == {exempt_id: motive, taxed_id: (None, None)}

    debit_note = await create_debit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id, customer_id=None,
        lines_input=[{"service_id": exempt_id, "quantity": 1}],
    )
    assert await _motives(db, debit_note.id) == {exempt_id: motive}

    pro_forma = await create_pro_forma(
        db, ctx["company"].id, ctx["activity"].id, None, [{"service_id": exempt_id, "quantity": 1}],
    )
    assert await _motives(db, pro_forma.id) == {exempt_id: motive}
