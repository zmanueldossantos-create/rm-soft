"""A raw material's packages (a 50 kg bag of flour) carry no price - it is never sold - so the price checks do not apply
to them; a second package with the same factor is still flagged."""
import uuid

import pytest

from app.models.product import Product, ProductType
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.product_sale_unit_service import (
    SaleUnitInvalidError, SaleUnitNeedsConfirmationError, create_sale_unit,
)


async def _flour(db, ctx):
    code = uuid.uuid4().hex[:4].upper()
    kilo = UnitOfMeasureCatalog(code="K" + code, name="Quilo " + code, is_fractional=True)
    bag = UnitOfMeasureCatalog(code="S" + code, name="Saco " + code)
    big = UnitOfMeasureCatalog(code="B" + code, name="Saco grande " + code)
    db.add_all([kilo, bag, big])
    await db.flush()
    flour = Product(company_id=ctx["company"].id, code="MP-" + code, name="Farinha " + code, vat_id=None, price=0,
                    purchase_price=750, min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True,
                    unit_of_measure_id=kilo.id)
    db.add(flour)
    ctx["company"].sale_unit_check_below_cost = "block"
    ctx["company"].sale_unit_check_same_factor = "warn"
    await db.commit()
    return flour.id, bag.id, big.id


@pytest.mark.asyncio
async def test_a_raw_material_package_needs_no_price(db, company_with_essentials):
    ctx = company_with_essentials
    flour_id, bag_id, _ = await _flour(db, ctx)
    package = await create_sale_unit(db, ctx["company"].id, flour_id, bag_id, 50, 0)
    assert float(package.price) == 0 and float(package.factor) == 50


@pytest.mark.asyncio
async def test_a_second_package_with_the_same_factor_is_still_flagged(db, company_with_essentials):
    ctx = company_with_essentials
    flour_id, bag_id, big_id = await _flour(db, ctx)
    await create_sale_unit(db, ctx["company"].id, flour_id, bag_id, 50, 0)
    with pytest.raises((SaleUnitNeedsConfirmationError, SaleUnitInvalidError)):
        await create_sale_unit(db, ctx["company"].id, flour_id, big_id, 50, 0)
