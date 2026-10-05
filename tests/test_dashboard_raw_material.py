"""A raw material is never sold: the stock summary values it at cost, but gives it no sale value and no margin, and
leaves it out of the potential margin."""
import uuid

import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.stock_service import get_stock_dashboard


@pytest.mark.asyncio
async def test_a_raw_material_has_no_sale_value_nor_margin(db, company_with_essentials):
    ctx = company_with_essentials
    code = uuid.uuid4().hex[:4].upper()
    flour = Product(company_id=ctx["company"].id, code="MP-" + code, name="Farinha " + code, vat_id=None, price=0,
                    min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True,
                    unit_of_measure_id=ctx["unit_un"].id, average_cost=100)
    db.add(flour)
    await db.flush()
    db.add(Stock(company_id=ctx["company"].id, product_id=flour.id, warehouse_id=ctx["activity_warehouse"].id, quantity=10))
    await db.commit()
    data = await get_stock_dashboard(db, ctx["company"].id)
    item = next(i for i in data["items"] if i["code"] == "MP-" + code)
    assert item["cost_value"] == 1000 and item["sale_value"] is None and item["margin_value"] is None
    assert data["total_margin_value"] == 0 and data["total_cost_value"] >= 1000
