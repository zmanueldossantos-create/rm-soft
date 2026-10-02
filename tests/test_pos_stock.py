"""The stock a point of sale sells from: its activity's warehouse, products managed by stock only."""
import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.pos_service import get_pos_stock


@pytest.mark.asyncio
async def test_the_till_reads_the_stock_of_its_activity_warehouse(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    managed = Product(company_id=company_id, code="PS-01", name="Gerido", vat_id=ctx["vat_nor"].id, price=10.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    free = Product(company_id=company_id, code="PS-02", name="Nao gerido", vat_id=ctx["vat_nor"].id, price=10.0,
                   min_stock_threshold=0, product_type=ProductType.BEM, managed_by_stock=False)
    db.add_all([managed, free])
    await db.commit()
    await db.refresh(managed)
    await db.refresh(free)
    db.add(Stock(company_id=company_id, product_id=managed.id, warehouse_id=ctx["activity_warehouse"].id, quantity=12))
    await db.commit()

    stock = await get_pos_stock(db, company_id, ctx["pos"].id)
    assert stock["warehouse_id"] == str(ctx["activity_warehouse"].id)
    assert stock["stock"][str(managed.id)] == 12.0
    assert str(free.id) not in stock["stock"]
