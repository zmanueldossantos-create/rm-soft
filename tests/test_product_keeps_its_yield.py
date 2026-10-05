"""The yield of a finished product belongs to its recipe: editing the product (its price, its name) never touches it."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.services.product_service import update_product


@pytest.mark.asyncio
async def test_editing_a_finished_product_keeps_its_yield(db, company_with_essentials):
    ctx = company_with_essentials
    code = "PAO-" + uuid.uuid4().hex[:4].upper()
    bread = Product(company_id=ctx["company"].id, code=code, name="Pao", vat_id=ctx["vat_nor"].id, price=100,
                    min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id, batch_yield=60)
    db.add(bread)
    await db.commit()
    await update_product(db, company_id=ctx["company"].id, product_id=bread.id, code=code, name="Pao de forma",
                         barcode=None, vat_id=ctx["vat_nor"].id, price=120, min_stock_threshold=0, expiry_date=None,
                         unit_of_measure_id=ctx["unit_un"].id)
    kept = (await db.execute(select(Product).where(Product.id == bread.id))).scalar_one()
    assert float(kept.batch_yield) == 60 and kept.name == "Pao de forma"
