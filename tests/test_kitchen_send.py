"""Point 34b - sending dishes to the kitchen: one order per sending (who, when, number of the day); the room may
lower or cancel a dish while it waits, never once the kitchen has started; a cancelled dish is never charged."""
import pytest
from sqlalchemy import select

from app.models.open_account_line import OpenAccountLine
from app.models.product import Product, ProductType
from app.services.open_account_service import (
    InvalidLineError, add_line, list_account_lines, list_open_accounts, open_account, remove_line,
    send_to_kitchen, update_line_quantity,
)


async def _setup(db, ctx):
    cid = ctx["company"].id
    dish = Product(company_id=cid, code="KIT-1", name="Muamba", vat_id=ctx["vat_ise"].id, price=4500, min_stock_threshold=0,
                   product_type=ProductType.BEM, managed_by_stock=False, prepared_in_kitchen=True)
    drink = Product(company_id=cid, code="KIT-2", name="Cuca", vat_id=ctx["vat_ise"].id, price=600, min_stock_threshold=0,
                    product_type=ProductType.BEM, managed_by_stock=False)
    db.add_all([dish, drink])
    await db.commit()
    table = await open_account(db, cid, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Mesa 1")
    return dish, drink, table


async def _add(db, ctx, table, product, quantity=1):
    return await add_line(db, ctx["company"].id, table.id, ctx["gestor"].id, quantity, product_id=product.id)


@pytest.mark.asyncio
async def test_dishes_wait_to_be_sent_drinks_never_go_to_the_kitchen(db, company_with_essentials):
    ctx = company_with_essentials
    dish, drink, table = await _setup(db, ctx)
    assert (await _add(db, ctx, table, dish)).kitchen_status == "NAO_ENVIADO"
    assert (await _add(db, ctx, table, drink)).kitchen_status is None


@pytest.mark.asyncio
async def test_one_sending_is_one_numbered_order_signed_by_its_sender(db, company_with_essentials):
    ctx = company_with_essentials
    dish, drink, table = await _setup(db, ctx)
    await _add(db, ctx, table, dish, 2)
    first = await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)
    await _add(db, ctx, table, dish)  # the same dish after the sending: a new line, for the next order
    second = await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)
    assert second.number == first.number + 1
    lines = await list_account_lines(db, table.id)
    assert sorted(float(l.quantity) for l in lines) == [1, 2]
    assert all(l.kitchen_status == "EM_ESPERA" and l.sent_by_name == ctx["gestor"].full_name for l in lines)
    with pytest.raises(InvalidLineError):
        await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)  # nothing left to send


@pytest.mark.asyncio
async def test_a_waiting_dish_may_be_lowered_or_cancelled_never_raised(db, company_with_essentials):
    ctx = company_with_essentials
    dish, drink, table = await _setup(db, ctx)
    line = await _add(db, ctx, table, dish, 2)
    await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)
    with pytest.raises(InvalidLineError):
        await update_line_quantity(db, ctx["company"].id, table.id, line.id, 3)
    line = await update_line_quantity(db, ctx["company"].id, table.id, line.id, 1)
    assert (float(line.quantity), line.kitchen_modified) == (1, True)
    await remove_line(db, ctx["company"].id, table.id, line.id)
    cancelled = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.id == line.id))).scalar_one()
    assert cancelled.kitchen_status == "ANULADO"  # struck through, still there for the kitchen


@pytest.mark.asyncio
async def test_once_the_kitchen_starts_the_room_changes_nothing(db, company_with_essentials):
    ctx = company_with_essentials
    dish, drink, table = await _setup(db, ctx)
    line = await _add(db, ctx, table, dish)
    await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)
    line.kitchen_status = "EM_PREPARACAO"
    await db.commit()
    with pytest.raises(InvalidLineError):
        await update_line_quantity(db, ctx["company"].id, table.id, line.id, 0)
    with pytest.raises(InvalidLineError):
        await remove_line(db, ctx["company"].id, table.id, line.id)


@pytest.mark.asyncio
async def test_a_cancelled_dish_is_never_charged(db, company_with_essentials):
    ctx = company_with_essentials
    dish, drink, table = await _setup(db, ctx)
    line = await _add(db, ctx, table, dish)
    await _add(db, ctx, table, drink)
    await send_to_kitchen(db, ctx["company"].id, table.id, ctx["gestor"].id)
    await remove_line(db, ctx["company"].id, table.id, line.id)
    account = next(a for a in await list_open_accounts(db, ctx["company"].id, ctx["activity"].id) if a.id == table.id)
    assert (account.line_count, account.total) == (1, 600)
