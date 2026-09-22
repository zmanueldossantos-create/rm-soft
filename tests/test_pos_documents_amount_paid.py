"""list_pos_documents exposes amount_paid = the real sum of Payment rows, not amount_received (which is None for FR)."""
import pytest

from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.invoice_service import create_invoice
from app.services.pos_documents_service import list_pos_documents


@pytest.mark.asyncio
async def test_amount_paid_reflects_real_payments_not_amount_received(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    service = Service(company_id=company_id, code="SRV-AP", name="Servico AP", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    fr = await create_invoice(  # 1140, paid on issue: real Payment rows, amount_received stays None
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=[{"service_id": service.id, "quantity": 1}], cash_session_id=session.id,
    )
    assert fr.amount_received is None

    documents = await list_pos_documents(db, company_id, pos_id, 30)
    found = next(d for d in documents if d.id == fr.id)
    assert found.amount_paid == 1140.0