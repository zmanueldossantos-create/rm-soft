"""The stock rules (one place, stock_service._stock_rule) and the sale guards (internal use, not available at the POS)."""
import pytest
from sqlalchemy import func, select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.stock_movement import StockMovement
from app.services.invoice_service import ProductNotFoundError, create_invoice
from app.services.pos_service import _ensure_sellable_at_pos
from app.services.stock_service import (
    StockBlockedError, _stock_rule, deduct_stock_for_sale, return_stock_for_credit_note,
)


async def _product(db, ctx, code, stock=None, **flags):
    product = Product(company_id=ctx["company"].id, code=code, name="Produto " + code, vat_id=ctx["vat_nor"].id,
                      price=100.0, min_stock_threshold=0, product_type=ProductType.BEM, **flags)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    if stock is not None:
        db.add(Stock(company_id=ctx["company"].id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=stock))
        await db.commit()
    return product


async def _freeze(db, ctx, entradas=False, saidas=False):
    warehouse = ctx["activity_warehouse"]
    warehouse.entradas_bloqueadas = entradas
    warehouse.saidas_bloqueadas = saidas
    await db.commit()


async def _movements(db, product_id):
    return (await db.execute(select(func.count(StockMovement.id)).where(StockMovement.product_id == product_id))).scalar_one()


@pytest.mark.asyncio
async def test_a_product_without_stock_is_sold_and_nothing_moves(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _product(db, ctx, "SEM-STOCK", managed_by_stock=False)
    await deduct_stock_for_sale(db, company_id=ctx["company"].id, warehouse_id=ctx["activity_warehouse"].id,
                                product_id=product.id, quantity=5, reference="FT TEST/1")
    assert await _movements(db, product.id) == 0


@pytest.mark.asyncio
async def test_a_warehouse_with_blocked_exits_refuses_a_sale(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _product(db, ctx, "SAI-BLOQ", stock=10)
    await _freeze(db, ctx, saidas=True)
    with pytest.raises(StockBlockedError, match="Saidas bloqueadas"):
        await deduct_stock_for_sale(db, company_id=ctx["company"].id, warehouse_id=ctx["activity_warehouse"].id,
                                    product_id=product.id, quantity=1, reference="FT TEST/2")


@pytest.mark.asyncio
async def test_blocked_entries_refuse_a_return_but_not_an_inventory_adjustment(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _product(db, ctx, "ENT-BLOQ", stock=10)
    await _freeze(db, ctx, entradas=True)
    with pytest.raises(StockBlockedError, match="Entradas bloqueadas"):
        await return_stock_for_credit_note(db, ctx["company"].id, ctx["activity_warehouse"].id, product.id, 1, "NC TEST/1")
    assert await _stock_rule(db, product.id, ctx["activity_warehouse"].id, "adjust", strict=True) is True


@pytest.mark.asyncio
async def test_an_internal_use_article_is_never_sold(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _product(db, ctx, "USO-INT", stock=10, internal_use_only=True)
    with pytest.raises(ProductNotFoundError, match="uso interno"):
        await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                             lines_input=[{"product_id": product.id, "quantity": 1}])


@pytest.mark.asyncio
async def test_an_article_not_available_at_the_pos_is_refused_at_the_caixa(db, company_with_essentials):
    ctx = company_with_essentials
    hidden = await _product(db, ctx, "NAO-POS", stock=10, not_available_pos=True)
    normal = await _product(db, ctx, "SIM-POS", stock=10)
    with pytest.raises(ProductNotFoundError, match="nao esta disponivel"):
        await _ensure_sellable_at_pos(db, ctx["company"].id, [{"product_id": hidden.id, "quantity": 1}])
    await _ensure_sellable_at_pos(db, ctx["company"].id, [{"product_id": str(normal.id), "quantity": 1}])
