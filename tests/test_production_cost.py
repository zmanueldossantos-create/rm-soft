"""The cost of a production: what is consumed (each ingredient at its average cost) becomes the cost of what is made,
folded into its average cost - flour at 1 875 Kz/kg makes bread at 625 Kz. An ingredient without a known cost never
blocks the production: the cost stays incomplete and the product's average cost is not touched."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.stock_movement import StockMovement
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.recipe_service import set_recipe
from app.services.stock_service import produce_stock


async def _bakery(db, ctx, flour_cost):
    code = uuid.uuid4().hex[:4].upper()
    kilo = UnitOfMeasureCatalog(code="K" + code, name="Quilo " + code, is_fractional=True)
    db.add(kilo)
    await db.flush()
    company_id, warehouse_id = ctx["company"].id, ctx["activity_warehouse"].id
    flour = Product(company_id=company_id, code="MP-" + code, name="Farinha " + code, vat_id=None, price=0,
                    min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=kilo.id,
                    average_cost=flour_cost)
    bread = Product(company_id=company_id, code="PAO-" + code, name="Pao " + code, vat_id=ctx["vat_nor"].id, price=1000,
                    min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([flour, bread])
    await db.flush()
    db.add(Stock(company_id=company_id, product_id=flour.id, warehouse_id=warehouse_id, quantity=40))
    await db.commit()
    await set_recipe(db, company_id, bread.id, 60, [{"ingredient_product_id": flour.id, "quantity_per_batch": 20}])
    return flour.id, bread.id


async def _output(db, bread_id):
    return (await db.execute(
        select(StockMovement).where(StockMovement.product_id == bread_id, StockMovement.is_production_output.is_(True))
    )).scalar_one()


@pytest.mark.asyncio
async def test_the_cost_of_what_is_consumed_becomes_the_cost_of_what_is_made(db, company_with_essentials):
    ctx = company_with_essentials
    _, bread_id = await _bakery(db, ctx, flour_cost=1875)
    await produce_stock(db, ctx["company"].id, ctx["activity_warehouse"].id, bread_id, 30)  # 10 kg of flour
    bread = (await db.execute(select(Product).where(Product.id == bread_id))).scalar_one()
    assert float(bread.average_cost) == 625  # 10 x 1 875 / 30
    assert float((await _output(db, bread_id)).unit_cost) == 625


@pytest.mark.asyncio
async def test_an_ingredient_without_cost_leaves_the_cost_incomplete(db, company_with_essentials):
    ctx = company_with_essentials
    _, bread_id = await _bakery(db, ctx, flour_cost=None)
    produced = await produce_stock(db, ctx["company"].id, ctx["activity_warehouse"].id, bread_id, 30)
    assert float(produced.quantity) == 30  # produced all the same
    bread = (await db.execute(select(Product).where(Product.id == bread_id))).scalar_one()
    assert bread.average_cost is None and (await _output(db, bread_id)).unit_cost is None
