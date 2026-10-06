"""Point 34c - the kitchen: its role, its board, and what it does with each dish."""
import pytest

from app.core.capabilities import capability_of_permission
from app.models.open_account import OpenAccountStatus
from app.models.product import Product, ProductType
from app.models.user import UserRole
from app.services.kitchen_service import KitchenItemNotFoundError, act_on_line, act_on_order, kitchen_board
from app.services.open_account_service import (
    InvalidLineError, add_line, list_open_accounts, open_account, send_to_kitchen,
)
from app.services.permission_service import EDITABLE_ROLES, PERMISSION_CATALOG

KITCHEN = {code for code, _, _, roles in PERMISSION_CATALOG if "COZINHA" in roles}


def test_the_kitchen_role_moves_dishes_and_never_cashes():
    assert UserRole("COZINHA").value == "COZINHA" and "COZINHA" in EDITABLE_ROLES
    assert {"kitchen:view", "kitchen:update"} <= KITCHEN
    assert not {c for c in KITCHEN if c.startswith(("open_accounts:", "pos:", "invoices:", "moedeiro:"))}
    assert capability_of_permission("kitchen:view") == "KITCHEN"


async def _sent_order(db, ctx, quantity=2):
    cid = ctx["company"].id
    dish = Product(company_id=cid, code="KB-" + str(quantity), name="Muamba", vat_id=ctx["vat_ise"].id, price=4500,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False, prepared_in_kitchen=True)
    db.add(dish)
    await db.commit()
    table = await open_account(db, cid, ctx["activity"].id, None, ctx["gestor"].id, "Mesa 1")
    line = await add_line(db, cid, table.id, ctx["gestor"].id, quantity, product_id=dish.id)
    order = await send_to_kitchen(db, cid, table.id, ctx["gestor"].id)
    return table, line, order


@pytest.mark.asyncio
async def test_a_sent_order_is_on_the_board_until_every_dish_is_ready(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    table, line, order = await _sent_order(db, ctx)
    board = await kitchen_board(db, cid)
    card = next(o for o in board["orders"] if o["id"] == order.id)
    assert (card["account_label"], card["sent_by_name"], card["lines"][0]["status"]) == ("Mesa 1", ctx["gestor"].full_name, "EM_ESPERA")
    board = await act_on_line(db, cid, line.id, "start")
    assert next(o for o in board["orders"] if o["id"] == order.id)["lines"][0]["status"] == "EM_PREPARACAO"
    board = await act_on_order(db, cid, order.id, "ready_all")
    assert all(o["id"] != order.id for o in board["orders"])
    assert any(o["id"] == order.id for o in board["recent"])
    account = next(a for a in await list_open_accounts(db, cid, ctx["activity"].id) if a.id == table.id)
    assert account.ready_dishes == 1


@pytest.mark.asyncio
async def test_the_kitchen_refuses_or_lowers_a_dish_but_never_raises_it(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    table, line, order = await _sent_order(db, ctx, quantity=3)
    with pytest.raises(InvalidLineError):
        await act_on_line(db, cid, line.id, "quantity", 4)
    board = await act_on_line(db, cid, line.id, "quantity", 2)
    dish = next(o for o in board["orders"] if o["id"] == order.id)["lines"][0]
    assert (dish["quantity"], dish["modified"]) == (2, True)
    board = await act_on_line(db, cid, line.id, "refuse")
    assert all(o["id"] != order.id for o in board["orders"])
    with pytest.raises(InvalidLineError):
        await act_on_line(db, cid, line.id, "ready")  # already cancelled


@pytest.mark.asyncio
async def test_a_dish_already_invoiced_is_never_cancelled_by_the_kitchen(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    table, line, order = await _sent_order(db, ctx)
    table.status = OpenAccountStatus.FECHADA
    await db.commit()
    with pytest.raises(InvalidLineError):
        await act_on_line(db, cid, line.id, "refuse")
    await act_on_line(db, cid, line.id, "ready")  # served after paying: still allowed


@pytest.mark.asyncio
async def test_another_company_never_reaches_a_dish(db, company_with_essentials):
    import uuid
    ctx = company_with_essentials
    table, line, order = await _sent_order(db, ctx)
    with pytest.raises(KitchenItemNotFoundError):
        await act_on_line(db, uuid.uuid4(), line.id, "ready")


@pytest.mark.asyncio
async def test_a_dish_moved_to_another_table_is_announced_where_it_is_now(db, company_with_essentials):
    from app.services.open_account_service import transfer_lines
    ctx = company_with_essentials
    cid, uid = ctx["company"].id, ctx["gestor"].id
    table, line, order = await _sent_order(db, ctx, quantity=1)
    other = await open_account(db, cid, ctx["activity"].id, None, uid, "Mesa 4")
    await transfer_lines(db, cid, table.id, uid, [{"line_id": line.id, "quantity": 1}], target_account_id=other.id)
    card = next(o for o in (await kitchen_board(db, cid))["orders"] if o["id"] == order.id)
    assert card["account_label"] == "Mesa 1"                # the order keeps the table it was sent from
    assert card["lines"][0]["account_label"] == "Mesa 4"    # the dish says where to serve it
