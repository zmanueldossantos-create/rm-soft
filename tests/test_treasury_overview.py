"""Point 9 (Tesouraria): the manager's view of every till - the cash of each till now (open: expected; closed: counted
at its last closing), the transfers in transit, the movements and the closings of a period."""
from datetime import date, timedelta

import pytest

from app.models.cash_movement import CashMovementStatus, CashMovementType
from app.models.cash_movement_reason import CashMovementReason
from app.models.movement_type import MovementDirection
from app.models.point_of_sale import PointOfSale
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_session_service import close_session, open_session
from app.services.treasury_overview_service import get_treasury_position, list_closings, list_treasury_movements


async def _three_tills(db, ctx):
    """Caixa Teste open with 7 000, Caixa 2 open empty, Caixa 3 closed with 300 counted; 2 000 sent to Caixa 2 (not
    received yet) and an entrada of 500 at Caixa Teste."""
    company_id, gestor = ctx["company"].id, ctx["gestor"]
    till_2 = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name="Caixa 2")
    till_3 = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name="Caixa 3")
    reason = CashMovementReason(company_id=company_id, name="Reforço", direction=MovementDirection.ENTRADA)
    db.add_all([till_2, till_3, reason])
    await db.commit()
    await open_session(db, company_id, ctx["pos"].id, gestor, 7000)
    await open_session(db, company_id, till_2.id, gestor, 0)
    closed = await open_session(db, company_id, till_3.id, gestor, 300)
    await close_session(db, company_id, closed.id, gestor.id, closing_amount_counted=250, closing_notes="Falta uma moeda")
    await create_cash_movement(db, company_id, CashMovementType.TRANSFERENCIA, gestor, 2000,
                               source_pos_id=ctx["pos"].id, destination_pos_id=till_2.id)
    await create_cash_movement(db, company_id, CashMovementType.ENTRADA_EXTERNA, gestor, 500,
                               destination_pos_id=ctx["pos"].id, reason_id=reason.id)
    return till_2, till_3


@pytest.mark.asyncio
async def test_the_position_shows_the_cash_of_every_till_and_the_transit(db, company_with_essentials):
    ctx = company_with_essentials
    till_2, till_3 = await _three_tills(db, ctx)
    position = await get_treasury_position(db, ctx["company"].id)
    by_name = {t["pos_name"]: t for t in position["tills"]}
    assert (by_name["Caixa Teste"]["is_open"], by_name["Caixa Teste"]["cash"], by_name["Caixa Teste"]["pending_out"]) == (True, 5500.0, 2000.0)
    assert (by_name["Caixa 2"]["cash"], by_name["Caixa 2"]["pending_in"]) == (0.0, 2000.0)  # not received yet
    assert (by_name["Caixa 3"]["is_open"], by_name["Caixa 3"]["cash"]) == (False, 250.0)  # counted at its closing
    assert by_name["Caixa Teste"]["opened_by"] == ctx["gestor"].full_name
    assert position["totals"] == {"cash": 5750.0, "in_transit": 2000.0, "open_tills": 2, "tills": 3}


@pytest.mark.asyncio
async def test_the_movements_are_named_and_filtered(db, company_with_essentials):
    ctx = company_with_essentials
    till_2, _ = await _three_tills(db, ctx)
    company_id = ctx["company"].id
    every = await list_treasury_movements(db, company_id)
    assert len(every) == 2
    pending = await list_treasury_movements(db, company_id, status=CashMovementStatus.PENDENTE)
    assert [(m["source"]["name"], m["destination"]["name"], m["amount"], m["received_by"]) for m in pending] == \
        [("Caixa Teste", "Caixa 2", 2000.0, None)]
    entradas = await list_treasury_movements(db, company_id, movement_type=CashMovementType.ENTRADA_EXTERNA)
    assert [(m["source"], m["destination"]["name"], m["reason"]) for m in entradas] == [(None, "Caixa Teste", "Reforço")]
    assert len(await list_treasury_movements(db, company_id, pos_id=till_2.id)) == 1  # either side of a transfer
    assert await list_treasury_movements(db, company_id, date_from=date.today() + timedelta(days=1)) == []


@pytest.mark.asyncio
async def test_the_closings_show_expected_counted_and_difference(db, company_with_essentials):
    ctx = company_with_essentials
    _, till_3 = await _three_tills(db, ctx)
    closings = await list_closings(db, ctx["company"].id)
    assert [(c["pos_name"], c["expected"], c["counted"], c["difference"], c["notes"]) for c in closings] == \
        [("Caixa 3", 300.0, 250.0, -50.0, "Falta uma moeda")]
    assert await list_closings(db, ctx["company"].id, pos_id=ctx["pos"].id) == []
