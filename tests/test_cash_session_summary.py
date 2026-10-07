"""The balance of a session, justified: every part of it adds up to the cash expected in the drawer, and a transfer
waiting for its reception is shown apart, never in the drawer."""
import uuid

import pytest

from app.models.cash_movement import CashMovementType
from app.models.point_of_sale import PointOfSale
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_session_service import get_session_summary, open_session


@pytest.mark.asyncio
async def test_the_summary_adds_up_to_the_drawer_and_keeps_pending_receptions_apart(db, company_with_essentials):
    setup = company_with_essentials
    company, gestor = setup["company"], setup["gestor"]
    other = PointOfSale(company_id=company.id, activity_id=setup["activity"].id, name=f"Caixa {uuid.uuid4().hex[:6]}")
    db.add(other)
    await db.commit()
    await open_session(db, company.id, other.id, gestor, opening_amount=500)
    await open_session(db, company.id, setup["pos"].id, gestor, opening_amount=1000)

    await create_cash_movement(db, company.id, CashMovementType.TRANSFERENCIA, gestor, amount=300,
                               source_pos_id=setup["pos"].id, destination_pos_id=other.id)
    await create_cash_movement(db, company.id, CashMovementType.TRANSFERENCIA, gestor, amount=200,
                               source_pos_id=other.id, destination_pos_id=setup["pos"].id)  # not yet received

    s = await get_session_summary(db, company.id, setup["pos"].id)
    assert s["transfers_out"] == 300 and s["pending_in"] == 200 and s["transfers_in"] == 0
    assert s["expected_cash"] == 700
    assert s["expected_cash"] == round(
        s["opening_amount"] + s["cash_sales"] + s["transfers_in"] + s["entries"] - s["transfers_out"] - s["exits"], 2)


@pytest.mark.asyncio
async def test_no_open_session_no_summary(db, company_with_essentials):
    setup = company_with_essentials
    assert await get_session_summary(db, setup["company"].id, setup["pos"].id) is None


@pytest.mark.asyncio
async def test_sales_are_split_by_payment_method_and_only_cash_goes_to_the_drawer(db, company_with_essentials):
    from sqlalchemy import text
    from app.models.service import Service
    from app.services.invoice_service import create_invoice

    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    multicaixa_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-SUM", name="Servico resumo", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    session = await open_session(db, company_id, ctx["pos"].id, ctx["gestor"], opening_amount=1000)

    for method_id in (ctx["pm_numerario"].id, multicaixa_id):  # 1140 each (1000 + IVA 14 %)
        await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO",
                             lines_input=[{"service_id": service.id, "quantity": 1}], amount_received=1140.0,
                             payment_method_id=method_id, cash_session_id=session.id)

    s = await get_session_summary(db, company_id, ctx["pos"].id)
    by_code = {m["code"]: m for m in s["by_method"]}
    assert by_code["MB"]["amount"] == 1140 and not by_code["MB"]["is_cash"]
    assert s["cash_sales"] == 1140 and s["total_received"] == 2280
    assert s["expected_cash"] == 2140  # the opening float + the cash sale only
