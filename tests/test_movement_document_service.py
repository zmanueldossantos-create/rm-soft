import pytest

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.movement_type import MovementType, MovementDirection
from app.services.movement_document_service import (
    create_stock_movement_document,
    InsufficientStockForMovementError,
)
from sqlalchemy import select

pytestmark = pytest.mark.asyncio


async def _make_product(db, company, vat, code="PROD-MV"):
    product = Product(
        company_id=company.id, code=code, name="Produto Movimento",
        vat_id=vat.id, price=100.0, min_stock_threshold=0,
        product_type=ProductType.BEM,
    )
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def _make_movement_type(db, code, direction):
    mt = MovementType(code=code, name=f"Teste {code}", direction=direction, is_auto=False)
    db.add(mt)
    await db.commit()
    await db.refresh(mt)
    return mt


async def test_create_stock_movement_document_entrada_increases_stock(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"])
    entrada_type = await _make_movement_type(db, "ENT", MovementDirection.ENTRADA)

    doc = await create_stock_movement_document(
        db, company.id, entrada_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 15, "purchase_price": 200.0, "sale_price": 250.0}],
    )

    assert doc.series == f"ENT{doc.movement_date.year}"
    assert doc.number == 1
    assert float(doc.total_quantity) == 15.0
    assert float(doc.total_value) == 3000.0  # 15 x 200 (purchase price, since ENTRADA)

    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock = stock_result.scalar_one()
    assert float(stock.quantity) == 15.0


async def test_create_stock_movement_document_saida_decreases_stock_and_rejects_insufficient(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    product = await _make_product(db, company, setup["vat_ise"], code="PROD-MV2")
    entrada_type = await _make_movement_type(db, "ENT2", MovementDirection.ENTRADA)
    saida_type = await _make_movement_type(db, "SAI2", MovementDirection.SAIDA)

    await create_stock_movement_document(
        db, company.id, entrada_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 10, "purchase_price": 50.0, "sale_price": 80.0}],
    )

    doc = await create_stock_movement_document(
        db, company.id, saida_type.id, setup["activity_warehouse"].id,
        lines_input=[{"product_id": product.id, "quantity": 4, "purchase_price": 50.0, "sale_price": 80.0}],
    )
    assert float(doc.total_value) == 320.0  # 4 x 80 (sale price, since SAIDA)

    stock_result = await db.execute(select(Stock).where(Stock.product_id == product.id, Stock.warehouse_id == setup["activity_warehouse"].id))
    stock = stock_result.scalar_one()
    assert float(stock.quantity) == 6.0  # 10 - 4

    with pytest.raises(InsufficientStockForMovementError):
        await create_stock_movement_document(
            db, company.id, saida_type.id, setup["activity_warehouse"].id,
            lines_input=[{"product_id": product.id, "quantity": 100, "purchase_price": 50.0, "sale_price": 80.0}],
        )
