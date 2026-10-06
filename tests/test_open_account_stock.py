"""Point 33bis - an open account is a till cart kept open: the stock is checked when an item is added,
against what is left in the warehouse of its point of sale once every open account is counted."""
import pytest

from app.models.open_account import OpenAccountStatus
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.open_account_service import (
    InsufficientStockError, add_line, open_account, update_line_quantity,
)
from app.services.pos_service import get_pos_stock


async def _product(db, ctx, code, stock=None, managed=True):
    product = Product(
        company_id=ctx["company"].id, code=code, name=code, vat_id=ctx["vat_ise"].id, price=600,
        min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=managed,
    )
    db.add(product)
    await db.flush()
    if stock is not None:
        db.add(Stock(company_id=ctx["company"].id, product_id=product.id,
                     warehouse_id=ctx["activity_warehouse"].id, quantity=stock))
    await db.commit()
    await db.refresh(product)
    return product


async def _negative(db, ctx, allowed):
    ctx["activity_warehouse"].allow_negative_stock = allowed
    await db.commit()


async def _account(db, ctx, label):
    return await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, label)


async def _add(db, ctx, account, product, quantity):
    return await add_line(db, ctx["company"].id, account.id, ctx["gestor"].id, quantity, product_id=product.id)


@pytest.mark.asyncio
async def test_adding_beyond_the_stock_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, False)
    beer = await _product(db, ctx, "OAS-1", stock=2)
    table = await _account(db, ctx, "Mesa 1")
    await _add(db, ctx, table, beer, 2)
    with pytest.raises(InsufficientStockError, match="Stock insuficiente"):
        await _add(db, ctx, table, beer, 1)


@pytest.mark.asyncio
async def test_two_tables_share_what_is_left(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, False)
    beer = await _product(db, ctx, "OAS-2", stock=3)
    table_a, table_b = await _account(db, ctx, "Mesa A"), await _account(db, ctx, "Mesa B")
    await _add(db, ctx, table_a, beer, 2)
    with pytest.raises(InsufficientStockError):
        await _add(db, ctx, table_b, beer, 2)  # only 1 left once table A is counted
    await _add(db, ctx, table_b, beer, 1)


@pytest.mark.asyncio
async def test_a_warehouse_allowing_negative_stock_never_blocks(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, True)
    beer = await _product(db, ctx, "OAS-3", stock=0)
    await _add(db, ctx, await _account(db, ctx, "Mesa 1"), beer, 5)


@pytest.mark.asyncio
async def test_lowering_a_quantity_always_passes_raising_it_is_checked(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, False)
    beer = await _product(db, ctx, "OAS-4", stock=2)
    table = await _account(db, ctx, "Mesa 1")
    line = await _add(db, ctx, table, beer, 2)
    with pytest.raises(InsufficientStockError):
        await update_line_quantity(db, ctx["company"].id, table.id, line.id, 3)
    line = await update_line_quantity(db, ctx["company"].id, table.id, line.id, 1)
    assert float(line.quantity) == 1


@pytest.mark.asyncio
async def test_a_product_without_stock_management_is_never_checked(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, False)
    dish = await _product(db, ctx, "OAS-5", managed=False)
    await _add(db, ctx, await _account(db, ctx, "Mesa 1"), dish, 10)


@pytest.mark.asyncio
async def test_the_till_sees_what_open_accounts_hold_as_gone(db, company_with_essentials):
    ctx = company_with_essentials
    await _negative(db, ctx, False)
    beer = await _product(db, ctx, "OAS-6", stock=48)
    table = await _account(db, ctx, "Mesa 1")
    await _add(db, ctx, table, beer, 2)
    stock = await get_pos_stock(db, ctx["company"].id, ctx["pos"].id)
    assert stock["stock"][str(beer.id)] == 46
    table.status = OpenAccountStatus.FECHADA  # a closed account no longer holds anything
    await db.commit()
    stock = await get_pos_stock(db, ctx["company"].id, ctx["pos"].id)
    assert stock["stock"][str(beer.id)] == 48
