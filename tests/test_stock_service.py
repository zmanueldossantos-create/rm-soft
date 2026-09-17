"""
Tests for stock_service - covers the two subtle bugs we hunted manually
this session: transfer direction correctness (is_transfer_source /
counterpart_warehouse_id), and production blocking when an ingredient is
insufficient (all-or-nothing, no partial deduction).
"""
import pytest

from app.models.product import Product, ProductType
from app.models.recipe_ingredient import RecipeIngredient
from app.models.stock import Stock
from app.services.stock_service import (
    receive_stock,
    transfer_stock,
    produce_stock,
    InsufficientStockError,
)
from sqlalchemy import select


async def _make_product(db, company, vat, code, is_raw_material=False, batch_yield=1):
    product = Product(
        company_id=company.id, code=code, name=f"Produto {code}",
        vat_id=vat.id, price=0, min_stock_threshold=0,
        product_type=ProductType.BEM, is_raw_material=is_raw_material, batch_yield=batch_yield,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def test_transfer_stock_moves_correct_direction(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], "FAR-001")
    await receive_stock(db, company.id, product.id, 20)  # into central

    await transfer_stock(
        db, company.id, product.id,
        from_warehouse_id=setup["central_warehouse"].id,
        to_warehouse_id=setup["activity_warehouse"].id,
        quantity=8,
    )

    central_result = await db.execute(
        select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["central_warehouse"].id)
    )
    activity_result = await db.execute(
        select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    central_stock = central_result.scalar_one()
    activity_stock = activity_result.scalar_one()

    assert float(central_stock.quantity) == 12  # 20 - 8
    assert float(activity_stock.quantity) == 8  # 0 + 8


async def test_transfer_stock_records_correct_source_and_counterpart(db, company_with_essentials):
    """The exact bug we found in production: direction must never be guessable from row order."""
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], "FAR-002")
    await receive_stock(db, company.id, product.id, 10)

    await transfer_stock(
        db, company.id, product.id,
        from_warehouse_id=setup["central_warehouse"].id,
        to_warehouse_id=setup["activity_warehouse"].id,
        quantity=5,
    )

    from app.models.stock_movement import StockMovement
    result = await db.execute(
        select(StockMovement).where(StockMovement.product_id == product.id, StockMovement.movement_type == "TRANSFERENCIA")
    )
    movements = {m.warehouse_id: m for m in result.scalars().all()}

    source_leg = movements[setup["central_warehouse"].id]
    dest_leg = movements[setup["activity_warehouse"].id]

    assert source_leg.is_transfer_source is True
    assert source_leg.counterpart_warehouse_id == setup["activity_warehouse"].id
    assert dest_leg.is_transfer_source is False
    assert dest_leg.counterpart_warehouse_id == setup["central_warehouse"].id


async def test_produce_stock_blocks_when_any_ingredient_insufficient(db, company_with_essentials):
    """All-or-nothing: if even ONE ingredient is short, nothing should be deducted or produced."""
    setup = company_with_essentials
    company = setup["company"]
    flour = await _make_product(db, company, setup["vat_ise"], "FAR-003", is_raw_material=True)
    salt = await _make_product(db, company, setup["vat_ise"], "SAL-003", is_raw_material=True)
    bread = await _make_product(db, company, setup["vat_ise"], "PAO-003", batch_yield=400)

    db.add_all([
        RecipeIngredient(company_id=company.id, finished_product_id=bread.id, ingredient_product_id=flour.id, quantity_per_batch=1),
        RecipeIngredient(company_id=company.id, finished_product_id=bread.id, ingredient_product_id=salt.id, quantity_per_batch=1),
    ])
    # Plenty of flour, but salt is short (0.5 instead of 1 needed for a full batch).
    db.add_all([
        Stock(company_id=company.id, product_id=flour.id, warehouse_id=setup["activity_warehouse"].id, quantity=10),
        Stock(company_id=company.id, product_id=salt.id, warehouse_id=setup["activity_warehouse"].id, quantity=0.5),
    ])
    await db.commit()

    with pytest.raises(InsufficientStockError):
        await produce_stock(db, company.id, setup["activity_warehouse"].id, bread.id, quantity_to_produce=400)

    # Flour must be untouched - no partial deduction from the ingredient that WAS sufficient.
    flour_result = await db.execute(
        select(Stock).where(Stock.product_id == flour.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    assert float(flour_result.scalar_one().quantity) == 10

    bread_result = await db.execute(
        select(Stock).where(Stock.product_id == bread.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    assert bread_result.scalar_one_or_none() is None  # nothing produced at all


async def test_produce_stock_succeeds_and_scales_by_batch(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    flour = await _make_product(db, company, setup["vat_ise"], "FAR-004", is_raw_material=True)
    bread = await _make_product(db, company, setup["vat_ise"], "PAO-004", batch_yield=400)

    db.add(RecipeIngredient(company_id=company.id, finished_product_id=bread.id, ingredient_product_id=flour.id, quantity_per_batch=1))
    db.add(Stock(company_id=company.id, product_id=flour.id, warehouse_id=setup["activity_warehouse"].id, quantity=3))
    await db.commit()

    # 0.5 batch (200 units) should consume 0.5 sacks of flour.
    await produce_stock(db, company.id, setup["activity_warehouse"].id, bread.id, quantity_to_produce=200)

    flour_result = await db.execute(
        select(Stock).where(Stock.product_id == flour.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    bread_result = await db.execute(
        select(Stock).where(Stock.product_id == bread.id, Stock.warehouse_id == setup["activity_warehouse"].id)
    )
    assert float(flour_result.scalar_one().quantity) == 2.5  # 3 - 0.5
    assert float(bread_result.scalar_one().quantity) == 200
