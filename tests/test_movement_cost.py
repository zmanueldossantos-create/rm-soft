"""
Every stock movement keeps the cost per base unit it took the goods at (the weighted average cost, else the purchase
price): a sale, a loss, a transfer, an adjustment - the value of what left the stock is known when it happened (the
cost of the sales, for the accounting). A credit note puts the goods back at the cost their sale took them out at.
"""
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock_movement import MovementType, StockMovement
from app.services.stock_service import (
    adjust_stock, deduct_stock_for_sale, record_stock_loss, receive_stock, return_stock_for_credit_note,
    transfer_stock,
)


async def _product(db, ctx, average_cost=150, purchase_price=None):
    product = Product(company_id=ctx["company"].id, code="CST-1", name="Farinha", vat_id=ctx["vat_ise"].id, price=300,
                      min_stock_threshold=0, product_type=ProductType.BEM, average_cost=average_cost,
                      purchase_price=purchase_price)
    db.add(product)
    await db.commit()
    return product


async def _costs(db, product_id, movement_type):
    return [float(c) if c is not None else None for c in (await db.execute(
        select(StockMovement.unit_cost).where(StockMovement.product_id == product_id,
                                              StockMovement.movement_type == movement_type)
    )).scalars().all()]


async def test_every_exit_keeps_its_cost(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, central, shop = ctx["company"].id, ctx["central_warehouse"].id, ctx["activity_warehouse"].id
    product = await _product(db, ctx)
    product_id = product.id
    await receive_stock(db, company_id, product_id, 20)
    await transfer_stock(db, company_id, product_id, central, shop, 8)
    await record_stock_loss(db, company_id, shop, product_id, 1, "QUEBRA")
    await adjust_stock(db, company_id, shop, product_id, 6, "Contagem")
    await deduct_stock_for_sale(db, company_id, shop, product_id, 2, "FR CST/1")
    await db.commit()

    assert await _costs(db, product_id, MovementType.TRANSFERENCIA) == [150.0, 150.0]
    assert await _costs(db, product_id, MovementType.PERDA) == [150.0]
    assert await _costs(db, product_id, MovementType.AJUSTE) == [150.0]
    assert await _costs(db, product_id, MovementType.SAIDA) == [150.0]


async def test_a_credit_note_returns_the_goods_at_their_sale_cost(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, shop = ctx["company"].id, ctx["activity_warehouse"].id
    product = await _product(db, ctx)
    product_id = product.id
    await receive_stock(db, company_id, product_id, 5, warehouse_id=shop)
    await deduct_stock_for_sale(db, company_id, shop, product_id, 2, "FR CST/2")
    product.average_cost = 200  # the cost moved since the sale
    await db.commit()
    await return_stock_for_credit_note(db, company_id, shop, product_id, 2, "NC CST/1", sale_reference="FR CST/2")
    await db.commit()
    returned = (await db.execute(select(StockMovement.unit_cost).where(StockMovement.reference == "NC CST/1"))).scalar_one()
    assert float(returned) == 150.0


async def test_without_average_cost_the_purchase_price_is_used(db, company_with_essentials):
    ctx = company_with_essentials
    product = await _product(db, ctx, average_cost=None, purchase_price=120)
    product_id = product.id
    await receive_stock(db, ctx["company"].id, product_id, 3, warehouse_id=ctx["activity_warehouse"].id)
    await deduct_stock_for_sale(db, ctx["company"].id, ctx["activity_warehouse"].id, product_id, 1, "FR CST/3")
    await db.commit()
    assert await _costs(db, product_id, MovementType.SAIDA) == [120.0]
