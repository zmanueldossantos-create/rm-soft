"""The internal consumption list shows why each item left the stock (the reason), not only what and how much."""
import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.consumption_reason_service import create_consumption_reason
from app.services.internal_consumption_service import list_consumptions, record_consumption


@pytest.mark.asyncio
async def test_the_list_carries_the_reason_name(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    product = Product(company_id=company_id, code="CI-001", name="Pão de água", vat_id=ctx["vat_nor"].id, price=100.0,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    db.add(Stock(company_id=company_id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=50))
    await db.commit()
    reason = await create_consumption_reason(db, company_id, "Pequeno-almoço dos hóspedes")

    await record_consumption(db, company_id, ctx["activity"].id, product.id, 10, reason.id, ctx["gestor"].id)

    rows = await list_consumptions(db, company_id)
    assert [(r["product_name"], r["quantity"], r["reason_name"]) for r in rows] == [("Pão de água", 10.0, "Pequeno-almoço dos hóspedes")]
