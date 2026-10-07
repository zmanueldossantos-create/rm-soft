"""Point 34d - kitchen history: every step of a dish is signed and timed, and the period adds them up."""
from datetime import date

import pytest

from app.models.product import Product, ProductType
from app.services.kitchen_service import act_on_line, kitchen_history
from app.services.open_account_service import (
    InvalidLineError, add_line, open_account, remove_line, send_to_kitchen,
)
from app.services.permission_service import PERMISSION_CATALOG


def test_the_history_is_the_managers_by_default():
    roles = {code: r for code, _, _, r in PERMISSION_CATALOG}
    assert roles["kitchen:history"] == []  # GESTOR is implicit; the kitchen may be given it in the matrix


@pytest.mark.asyncio
async def test_every_step_is_signed_and_the_period_adds_them_up(db, company_with_essentials):
    ctx = company_with_essentials
    cid, uid = ctx["company"].id, ctx["gestor"].id
    dish = Product(company_id=cid, code="KH-1", name="Muamba", vat_id=ctx["vat_ise"].id, price=4500, min_stock_threshold=0,
                   product_type=ProductType.BEM, managed_by_stock=False, prepared_in_kitchen=True)
    other = Product(company_id=cid, code="KH-2", name="Calulu", vat_id=ctx["vat_ise"].id, price=5000, min_stock_threshold=0,
                    product_type=ProductType.BEM, managed_by_stock=False, prepared_in_kitchen=True)
    third = Product(company_id=cid, code="KH-3", name="Frango", vat_id=ctx["vat_ise"].id, price=4000, min_stock_threshold=0,
                    product_type=ProductType.BEM, managed_by_stock=False, prepared_in_kitchen=True)
    db.add_all([dish, other, third])
    await db.commit()
    table = await open_account(db, cid, ctx["activity"].id, None, uid, "Mesa 1")
    muamba = await add_line(db, cid, table.id, uid, 1, product_id=dish.id)
    calulu = await add_line(db, cid, table.id, uid, 1, product_id=other.id)
    frango = await add_line(db, cid, table.id, uid, 1, product_id=third.id)
    order = await send_to_kitchen(db, cid, table.id, uid)

    await act_on_line(db, cid, muamba.id, "start", user_id=uid)
    await act_on_line(db, cid, muamba.id, "ready", user_id=uid)
    await act_on_line(db, cid, calulu.id, "refuse", user_id=uid)          # the kitchen: sold out
    await remove_line(db, cid, table.id, frango.id, uid)                   # the room: cancelled while waiting

    today = date.today()
    history = await kitchen_history(db, cid, today, today)
    assert history["summary"] == {"orders": 1, "served": 1, "cancelled": 2, "sold_out": 1,
                                  "average_wait_minutes": history["summary"]["average_wait_minutes"]}
    card = next(o for o in history["orders"] if o["id"] == order.id)
    lines = {l["name"]: l for l in card["lines"]}
    assert lines["Muamba"]["started_by_name"] == lines["Muamba"]["ready_by_name"] == ctx["gestor"].full_name
    assert lines["Muamba"]["prep_minutes"] is not None and card["total_minutes"] is not None
    assert (lines["Calulu"]["cancel_reason"], lines["Calulu"]["cancelled_by_name"]) == ("Esgotado - cozinha", ctx["gestor"].full_name)
    assert (lines["Frango"]["cancel_reason"], lines["Frango"]["cancelled_by_name"]) == ("Anulado pela sala", ctx["gestor"].full_name)
    assert (card["dishes"], card["cancelled"]) == (1, 2)


@pytest.mark.asyncio
async def test_a_period_is_bounded(db, company_with_essentials):
    ctx = company_with_essentials
    with pytest.raises(InvalidLineError):
        await kitchen_history(db, ctx["company"].id, date(2026, 1, 1), date(2026, 6, 1))   # more than 92 days
    with pytest.raises(InvalidLineError):
        await kitchen_history(db, ctx["company"].id, date(2026, 2, 1), date(2026, 1, 1))   # upside down
