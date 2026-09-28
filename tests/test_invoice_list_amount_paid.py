"""list_invoices (the Faturas list) exposes amount_paid = the real sum of Payment rows, like the Caixa documents table:
amount_received stays None on a Fatura/Recibo paid at the till, so the list cannot rely on it alone."""
import pytest

from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.invoice_service import create_invoice, list_invoices


@pytest.mark.asyncio
async def test_list_invoices_exposes_the_real_amount_paid(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    service = Service(company_id=company_id, code="SRV-LI", name="Servico LI", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    fr = await create_invoice(  # 1140, paid on issue at the till: real Payment rows, amount_received stays None
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"service_id": service.id, "quantity": 1}], cash_session_id=session.id,
    )
    assert fr.amount_received is None

    listed = await list_invoices(db, company_id)
    found = next(i for i in listed if i.id == fr.id)
    assert found.amount_paid == 1140.0