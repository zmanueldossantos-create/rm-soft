"""The image of a product has its own routes (upload, removal): editing the product (its price, its name) never
loses it - a save from the screen used to overwrite the path just written by the upload."""
import uuid

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.services.product_service import update_product


@pytest.mark.asyncio
async def test_editing_a_product_keeps_its_image(db, company_with_essentials):
    ctx = company_with_essentials
    code = "IMG-" + uuid.uuid4().hex[:4].upper()
    path = "/uploads/products/" + uuid.uuid4().hex + ".png"
    cola = Product(company_id=ctx["company"].id, code=code, name="Cola", vat_id=ctx["vat_nor"].id, price=500,
                   min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id,
                   image_path=path)
    db.add(cola)
    await db.commit()
    await update_product(db, company_id=ctx["company"].id, product_id=cola.id, code=code, name="Cola 33cl",
                         barcode=None, vat_id=ctx["vat_nor"].id, price=550, min_stock_threshold=0, expiry_date=None,
                         unit_of_measure_id=ctx["unit_un"].id)
    kept = (await db.execute(select(Product).where(Product.id == cola.id))).scalar_one()
    assert kept.image_path == path and kept.name == "Cola 33cl" and float(kept.price) == 550
