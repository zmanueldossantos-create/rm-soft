"""list_invoices with pos_id restricts real invoices to that POS's sessions - pro-formas are always unscoped."""
import pytest

from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.invoice_service import create_invoice, create_pro_forma, list_invoices


async def _make_second_pos(db, company_id, activity_id):
    from app.models.point_of_sale import PointOfSale
    pos = PointOfSale(company_id=company_id, activity_id=activity_id, name="Segunda caixa", is_default=False, billetage_enabled=False)
    db.add(pos)
    await db.commit()
    await db.refresh(pos)
    return pos


@pytest.mark.asyncio
async def test_pos_id_scopes_real_invoices_but_not_pro_formas(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_a, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    pos_b = (await _make_second_pos(db, company_id, activity_id)).id

    service = Service(company_id=company_id, code="SRV-SCOPE", name="Servico Scope", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]

    session_a = await open_session(db, company_id, pos_a, gestor, opening_amount=0)
    invoice_a = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=lines, cash_session_id=session_a.id,
    )
    session_b = await open_session(db, company_id, pos_b, gestor, opening_amount=0)
    invoice_b = await create_invoice(
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
        lines_input=lines, cash_session_id=session_b.id,
    )
    pro_forma = await create_pro_forma(db, company_id, activity_id, None, lines)

    scoped_to_a = await list_invoices(db, company_id, pos_id=pos_a)
    ids_a = {inv.id for inv in scoped_to_a}
    assert invoice_a.id in ids_a
    assert invoice_b.id not in ids_a
    assert pro_forma.id in ids_a  # pro-formas always visible regardless of pos_id

    unscoped = await list_invoices(db, company_id)
    ids_all = {inv.id for inv in unscoped}
    assert invoice_a.id in ids_all and invoice_b.id in ids_all and pro_forma.id in ids_all