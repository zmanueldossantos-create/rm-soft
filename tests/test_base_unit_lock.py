"""The base unit of a product can be corrected while it has no history, never afterwards."""
import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.services.product_service import BaseUnitLockedError, ensure_base_unit_can_change
from app.services.stock_service import adjust_stock


@pytest.mark.asyncio
async def test_the_base_unit_is_locked_by_a_history(db, company_with_essentials):
    ctx = company_with_essentials
    unit = UnitOfMeasureCatalog(code="BUL1", name="Unidade teste bloqueio")
    db.add(unit)
    product = Product(company_id=ctx["company"].id, code="BU-01", name="Produto bloqueio", vat_id=ctx["vat_nor"].id, price=10.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(unit)
    await db.refresh(product)

    await ensure_base_unit_can_change(db, product, unit.id)  # no history yet: allowed

    db.add(Stock(company_id=ctx["company"].id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=0))
    await db.commit()
    await adjust_stock(db, ctx["company"].id, ctx["activity_warehouse"].id, product.id, 5, "Contagem inicial")
    with pytest.raises(BaseUnitLockedError, match="movimentos de stock"):
        await ensure_base_unit_can_change(db, product, unit.id)
