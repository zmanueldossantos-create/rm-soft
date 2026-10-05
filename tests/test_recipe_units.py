"""Recipes and production in units: a recipe typed in packages (1 lot = 2 CX of bread, 1 SC of flour) is kept in base
units with what was typed beside it, and a production asked in packages consumes the right quantities."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.product_sale_unit_service import create_sale_unit
from app.services.recipe_service import set_recipe
from app.services.stock_service import produce_stock


async def _bakery(db, ctx):
    code = uuid.uuid4().hex[:4].upper()
    kilo = UnitOfMeasureCatalog(code="K" + code, name="Quilo " + code, is_fractional=True)
    bag = UnitOfMeasureCatalog(code="S" + code, name="Saco " + code)
    box = UnitOfMeasureCatalog(code="C" + code, name="Caixa " + code)
    db.add_all([kilo, bag, box])
    await db.flush()
    company_id = ctx["company"].id
    flour = Product(company_id=company_id, code="MP-" + code, name="Farinha " + code, vat_id=None, price=0,
                    min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=kilo.id)
    bread = Product(company_id=company_id, code="PAO-" + code, name="Pao " + code, vat_id=ctx["vat_nor"].id, price=100,
                    min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([flour, bread])
    await db.flush()
    db.add(Stock(company_id=company_id, product_id=flour.id, warehouse_id=ctx["activity_warehouse"].id, quantity=100))
    await db.commit()
    sack = await create_sale_unit(db, company_id, flour.id, bag.id, 20, 0)
    crate = await create_sale_unit(db, company_id, bread.id, box.id, 30, 3000)
    return flour.id, bread.id, sack.id, crate.id


@pytest.mark.asyncio
async def test_a_recipe_typed_in_packages_is_kept_in_base_units(db, company_with_essentials):
    ctx = company_with_essentials
    flour_id, bread_id, sack_id, crate_id = await _bakery(db, ctx)
    rows = await set_recipe(db, ctx["company"].id, bread_id, 2,
                            [{"ingredient_product_id": flour_id, "quantity_per_batch": 1, "sale_unit_id": sack_id}],
                            batch_yield_sale_unit_id=crate_id)
    assert float(rows[0].quantity_per_batch) == 20 and float(rows[0].entry_quantity) == 1 and rows[0].entry_sale_unit_id == sack_id
    bread = (await db.execute(select(Product).where(Product.id == bread_id))).scalar_one()
    assert float(bread.batch_yield) == 60 and float(bread.batch_yield_entry) == 2 and bread.batch_yield_sale_unit_id == crate_id


@pytest.mark.asyncio
async def test_a_production_asked_in_packages_consumes_the_right_quantities(db, company_with_essentials):
    ctx = company_with_essentials
    flour_id, bread_id, sack_id, crate_id = await _bakery(db, ctx)
    await set_recipe(db, ctx["company"].id, bread_id, 2,
                     [{"ingredient_product_id": flour_id, "quantity_per_batch": 1, "sale_unit_id": sack_id}],
                     batch_yield_sale_unit_id=crate_id)
    produced = await produce_stock(db, ctx["company"].id, ctx["activity_warehouse"].id, bread_id, 5, sale_unit_id=crate_id)
    assert float(produced.quantity) == 150  # 5 CX of 30
    flour_stock = (await db.execute(
        select(Stock).where(Stock.product_id == flour_id, Stock.warehouse_id == ctx["activity_warehouse"].id)
    )).scalar_one()
    assert float(flour_stock.quantity) == 50  # 150 / 60 per lot = 2.5 lots x 20 kg
