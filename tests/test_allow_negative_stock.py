"""deduct_stock_for_sale respects the selling warehouse's allow_negative_stock: refuses by default,
lets the sale go through (stock ends up negative) when the warehouse explicitly allows it."""
import pytest

from app.models.product import Product, ProductType
from app.services.invoice_service import InsufficientStockError
from app.services.stock_service import _get_or_create_stock_row, deduct_stock_for_sale


async def _make_product(db, company_id, vat_id):
    product = Product(company_id=company_id, code="STK-NEG", name="Produto Teste Negativo", price=1000.0, vat_id=vat_id, product_type=ProductType.BEM)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


@pytest.mark.asyncio
async def test_refused_by_default_when_warehouse_disallows_negative(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, warehouse_id = ctx["company"].id, ctx["central_warehouse"].id
    product = await _make_product(db, company_id, ctx["vat_nor"].id)

    with pytest.raises(InsufficientStockError):
        await deduct_stock_for_sale(db, company_id=company_id, warehouse_id=warehouse_id, product_id=product.id, quantity=50, reference="test")


@pytest.mark.asyncio
async def test_allowed_and_goes_negative_when_warehouse_permits(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, warehouse = ctx["company"].id, ctx["central_warehouse"]
    product = await _make_product(db, company_id, ctx["vat_nor"].id)

    warehouse.allow_negative_stock = True
    await db.commit()

    await deduct_stock_for_sale(db, company_id=company_id, warehouse_id=warehouse.id, product_id=product.id, quantity=50, reference="test")
    stock = await _get_or_create_stock_row(db, company_id, product.id, warehouse.id)
    assert float(stock.quantity) == -50.0