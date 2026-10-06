"""Point 33bis - the lines of an open account are sold in units and packages, as in the till cart:
a CX of 24 is priced as the CX, takes 24 units of stock, and keeps its unit through a change or a transfer."""
import uuid

import pytest
from sqlalchemy import select

from app.models.open_account_line import OpenAccountLine
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.open_account_service import (
    InsufficientStockError, InvalidLineError, add_line, change_line_unit, open_account, transfer_lines,
    update_line_quantity,
)
from app.services.pos_service import get_pos_stock
from app.services.product_sale_unit_service import create_sale_unit


async def _cuca(db, ctx, stock):
    """A beer sold by the unit (600) and by the crate of 24 (13 500), with `stock` units on the shelf."""
    ctx["activity_warehouse"].allow_negative_stock = False
    code = uuid.uuid4().hex[:4].upper()
    box = UnitOfMeasureCatalog(code="X" + code, name="Caixa " + code)
    db.add(box)
    await db.flush()
    cuca = Product(company_id=ctx["company"].id, code="CUC-" + code, name="Cuca " + code, vat_id=ctx["vat_nor"].id,
                   price=600, min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(cuca)
    await db.flush()
    db.add(Stock(company_id=ctx["company"].id, product_id=cuca.id, warehouse_id=ctx["activity_warehouse"].id, quantity=stock))
    await db.commit()
    crate = await create_sale_unit(db, ctx["company"].id, cuca.id, box.id, 24, 13500)
    return cuca, crate, box.code


async def _account(db, ctx, label):
    return await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, label)


async def _add(db, ctx, account, product, quantity, sale_unit=None):
    return await add_line(db, ctx["company"].id, account.id, ctx["gestor"].id, quantity,
                          product_id=product.id, sale_unit_id=sale_unit.id if sale_unit else None)


async def _left(db, ctx, product):
    return (await get_pos_stock(db, ctx["company"].id, ctx["pos"].id))["stock"][str(product.id)]


@pytest.mark.asyncio
async def test_a_crate_line_is_priced_as_the_crate_and_takes_24_units(db, company_with_essentials):
    ctx = company_with_essentials
    cuca, crate, box_code = await _cuca(db, ctx, 48)
    line = await _add(db, ctx, await _account(db, ctx, "Mesa 1"), cuca, 1, crate)
    assert float(line.unit_price) == 13500
    assert float(line.unit_factor) == 24
    assert line.unit_code_snapshot == box_code
    assert await _left(db, ctx, cuca) == 24


@pytest.mark.asyncio
async def test_a_crate_needs_its_whole_content_in_stock(db, company_with_essentials):
    ctx = company_with_essentials
    cuca, crate, _ = await _cuca(db, ctx, 23)
    table = await _account(db, ctx, "Mesa 1")
    with pytest.raises(InsufficientStockError):
        await _add(db, ctx, table, cuca, 1, crate)
    await _add(db, ctx, table, cuca, 23)  # the units themselves are there


@pytest.mark.asyncio
async def test_the_same_beer_in_units_and_in_crates_makes_two_lines(db, company_with_essentials):
    ctx = company_with_essentials
    cuca, crate, _ = await _cuca(db, ctx, 48)
    table = await _account(db, ctx, "Mesa 1")
    await _add(db, ctx, table, cuca, 1)
    await _add(db, ctx, table, cuca, 1, crate)
    await _add(db, ctx, table, cuca, 1)  # merged into the unit line, as in the till cart
    lines = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == table.id))).scalars().all()
    assert sorted((float(l.quantity), float(l.unit_factor)) for l in lines) == [(1, 24), (2, 1)]
    assert await _left(db, ctx, cuca) == 22


@pytest.mark.asyncio
async def test_switching_a_line_to_crates_follows_price_and_stock(db, company_with_essentials):
    ctx = company_with_essentials
    cuca, crate, box_code = await _cuca(db, ctx, 47)
    table = await _account(db, ctx, "Mesa 1")
    line = await _add(db, ctx, table, cuca, 2)
    with pytest.raises(InsufficientStockError):  # 2 CX = 48 units, only 47 on the shelf
        await change_line_unit(db, ctx["company"].id, table.id, line.id, crate.id)
    line = await update_line_quantity(db, ctx["company"].id, table.id, line.id, 1)  # back to 1 unit
    with pytest.raises(InvalidLineError):
        await _add(db, ctx, table, cuca, -1)  # an addition is never negative
    line = await change_line_unit(db, ctx["company"].id, table.id, line.id, crate.id)
    assert (float(line.quantity), float(line.unit_factor), float(line.unit_price)) == (1, 24, 13500)
    assert line.unit_code_snapshot == box_code
    line = await change_line_unit(db, ctx["company"].id, table.id, line.id, None)  # back to the unit
    assert (float(line.unit_factor), float(line.unit_price)) == (1, 600)


@pytest.mark.asyncio
async def test_a_partial_transfer_keeps_the_crate(db, company_with_essentials):
    ctx = company_with_essentials
    cuca, crate, box_code = await _cuca(db, ctx, 48)
    src, dst = await _account(db, ctx, "Mesa 1"), await _account(db, ctx, "Mesa 2")
    line = await _add(db, ctx, src, cuca, 2, crate)
    await transfer_lines(db, ctx["company"].id, src.id, ctx["gestor"].id,
                         [{"line_id": line.id, "quantity": 1}], target_account_id=dst.id)
    moved = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == dst.id))).scalars().one()
    assert moved.sale_unit_id == crate.id
    assert (float(moved.quantity), float(moved.unit_factor), float(moved.unit_price)) == (1, 24, 13500)
    assert moved.unit_code_snapshot == box_code
    assert await _left(db, ctx, cuca) == 0  # still 2 crates on the open accounts
