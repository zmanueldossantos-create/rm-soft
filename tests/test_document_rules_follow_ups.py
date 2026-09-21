"""NC, ND and receipts follow the accepts_* rules of the document they refer to, not its name."""
import pytest
from sqlalchemy import select, text

from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.invoice_service import (
    ReferenceInvoiceTypeNotEligibleError, create_credit_note, create_debit_note, create_invoice, create_receipt,
)


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


async def _service(db, ctx, code):
    service = Service(company_id=ctx["company"].id, code=code, name="Servico " + code, price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service.id


@pytest.mark.asyncio
async def test_follow_up_documents_follow_the_accepts_rules(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service_id = await _service(db, ctx, "SRV-FU")
    ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA",
                              lines_input=[{"service_id": service_id, "quantity": 2}])
    ft_id = ft.id
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == ft_id))).scalar_one()

    async def credit():
        return await create_credit_note(db, company_id, activity_id, reference_invoice_id=ft_id, credit_note_reason="RTF",
                                        credit_note_cause="Teste", lines_input=[{"invoice_line_id": line_id, "quantity": 1}])

    async def debit():
        return await create_debit_note(db, company_id, activity_id, customer_id=None, reference_invoice_id=ft_id,
                                       lines_input=[{"service_id": service_id, "quantity": 1}])

    async def receipt():
        return await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=100.0)

    for make in (credit, debit, receipt):  # accepted by a Factura
        await make()
    for rule, make in (("accepts_credit_note", credit), ("accepts_debit_note", debit), ("accepts_receipt", receipt)):
        try:
            await _set_rule(db, "FT", **{rule: False})
            with pytest.raises(ReferenceInvoiceTypeNotEligibleError):
                await make()
        finally:
            await _set_rule(db, "FT", **{rule: True})


@pytest.mark.asyncio
async def test_a_receipt_on_a_fatura_recibo_follows_the_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service_id = await _service(db, ctx, "SRV-FQ")
    fr = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
                              lines_input=[{"service_id": service_id, "quantity": 1}])
    fr_id = fr.id
    with pytest.raises(ReferenceInvoiceTypeNotEligibleError):  # refused by the catalog rule
        await create_receipt(db, company_id, activity_id, reference_invoice_id=fr_id, amount=100.0)
    try:
        await _set_rule(db, "FR", accepts_receipt=True)
        receipt = await create_receipt(db, company_id, activity_id, reference_invoice_id=fr_id, amount=100.0)
        assert float(receipt.amount_received) == 100.0
    finally:
        await _set_rule(db, "FR", accepts_receipt=False)