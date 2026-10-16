"""
Lots et péremption (point 4): a product followed by lot / expiry enters the stock with its lot (number and/or date, as
required), every exit takes the lots FEFO - never an expired one on a sale - and the lots travel with the goods
(transfer) or come back where they were taken from (credit note, cancelled purchase, cancelled guide). The lots of a
warehouse always add up to its stock; a warehouse allowing negative stock fills its gap first on the next entry.
Following a product by lot is switched on or off only with its stock at zero.
"""
import uuid
from datetime import date, timedelta

import pytest
from sqlalchemy import select

from app.models.customer import Customer, LegalPersonType
from app.models.document_type import DocumentType
from app.models.invoice_line import InvoiceLine
from app.models.legal_vat_rate import LegalVatRate
from app.models.movement_type import MovementDirection, MovementType as MovementTypeCatalog
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.stock_lot import StockLot
from app.models.supplier import Supplier
from app.services.goods_movement_service import cancel_goods_movement, create_goods_movement
from app.services.invoice_service import StockUnavailableError, create_credit_note, create_invoice
from app.services.pos_service import get_pos_stock
from app.services.product_service import LotTrackingLockedError, ensure_lot_tracking_can_change
from app.services.purchase_invoice_service import PurchaseInvoiceError, cancel_purchase_invoice, register_purchase_invoice
from app.services.recipe_service import set_recipe
from app.services.stock_service import (
    InsufficientStockError, adjust_stock, produce_stock, receive_stock, record_stock_loss, transfer_stock,
)

TODAY = date.today()


async def _product(db, ctx, batch=True, expiry=True, name="Iogurte"):
    product = Product(company_id=ctx["company"].id, code=name[:3].upper() + uuid.uuid4().hex[:4], name=name,
                      vat_id=ctx["vat_nor"].id, price=500, min_stock_threshold=0, product_type=ProductType.BEM,
                      unit_of_measure_id=ctx["unit_un"].id, managed_by_batch=batch, managed_by_expiry=expiry)
    db.add(product)
    await db.commit()
    return product.id


async def _lots(db, product_id, warehouse_id):
    """{label: quantity} of the lots still holding stock, and the warehouse's stock."""
    lots = (await db.execute(select(StockLot).where(StockLot.product_id == product_id, StockLot.warehouse_id == warehouse_id,
                                                    StockLot.quantity > 0))).scalars().all()
    stock = (await db.execute(select(Stock.quantity).where(Stock.product_id == product_id,
                                                           Stock.warehouse_id == warehouse_id))).scalar_one_or_none()
    return {(l.lot_number or "-"): float(l.quantity) for l in lots}, float(stock or 0)


async def _sell(db, ctx, product_id, quantity):
    ids = ctx.get("_ids") or (ctx["company"].id, ctx["activity"].id)  # set early in a test where a refusal rolls back
    return await create_invoice(db, ids[0], ids[1], customer_id=None, invoice_type="FACTURA",
                                lines_input=[{"product_id": product_id, "quantity": quantity}])


async def _purchase_setup(db, ctx):
    supplier = Supplier(company_id=ctx["company"].id, name="Lacticínios Lda", nif="5000999111")
    rate = (await db.execute(select(LegalVatRate).where(LegalVatRate.tax_category == "NOR"))).scalar_one_or_none()
    if rate is None:
        rate = LegalVatRate(tax_category="NOR", name="NOR", rate=14)
    db.add_all([supplier, rate,
                MovementTypeCatalog(code="EAL", name="Entrada automática", direction=MovementDirection.ENTRADA, is_auto=True),
                MovementTypeCatalog(code="SAL", name="Saída automática", direction=MovementDirection.SAIDA, is_auto=True)])
    await db.commit()
    return supplier.id, rate.id


def _line(product_id, rate_id, quantity, lot=None, days=None):
    return {"product_id": product_id, "quantity": quantity, "unit_price": 300, "legal_vat_rate_id": rate_id,
            "lot_number": lot, "expiry_date": TODAY + timedelta(days=days) if days is not None else None}


@pytest.mark.asyncio
async def test_a_purchase_enters_its_lots_and_a_sale_takes_the_first_to_expire(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id, shop = ctx["company"].id, ctx["gestor"].id, ctx["activity_warehouse"].id
    ctx["_ids"] = (company_id, ctx["activity"].id)
    product_id = await _product(db, ctx)
    supplier_id, rate_id = await _purchase_setup(db, ctx)

    with pytest.raises(PurchaseInvoiceError, match="Indique o lote de Iogurte"):
        await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/1", TODAY,
                                        [_line(product_id, rate_id, 10, days=10)], stock_entry=True, warehouse_id=shop)
    with pytest.raises(PurchaseInvoiceError, match="Indique a validade de Iogurte"):
        await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/1", TODAY,
                                        [_line(product_id, rate_id, 10, lot="L2")], stock_entry=True, warehouse_id=shop)
    with pytest.raises(PurchaseInvoiceError, match="já passou"):
        await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/1", TODAY,
                                        [_line(product_id, rate_id, 10, lot="L2", days=-1)], stock_entry=True, warehouse_id=shop)
    await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/1", TODAY,
                                    [_line(product_id, rate_id, 10, lot="L2", days=20),
                                     _line(product_id, rate_id, 10, lot="L1", days=5)], stock_entry=True, warehouse_id=shop)
    assert await _lots(db, product_id, shop) == ({"L1": 10.0, "L2": 10.0}, 20.0)

    await _sell(db, ctx, product_id, 12)  # L1 (expires first) then L2
    assert await _lots(db, product_id, shop) == ({"L2": 8.0}, 8.0)


@pytest.mark.asyncio
async def test_an_expired_lot_is_never_sold_and_is_written_off_first(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, shop, pos_id = ctx["company"].id, ctx["activity_warehouse"].id, ctx["pos"].id
    ctx["_ids"] = (company_id, ctx["activity"].id)
    product_id = await _product(db, ctx)
    await receive_stock(db, company_id, product_id, 4, lot_number="OLD", expiry_date=TODAY, warehouse_id=shop)
    await receive_stock(db, company_id, product_id, 3, lot_number="NEW", expiry_date=TODAY + timedelta(days=30), warehouse_id=shop)
    old = (await db.execute(select(StockLot).where(StockLot.lot_number == "OLD"))).scalar_one()
    old.expiry_date = TODAY - timedelta(days=1)  # time passes
    await db.commit()

    pos_stock = await get_pos_stock(db, company_id, pos_id)
    assert pos_stock["stock"][str(product_id)] == 3.0  # the till only sees what can be sold
    with pytest.raises(StockUnavailableError, match=r"disponível: 3; 4 expirado - registe a perda"):
        await _sell(db, ctx, product_id, 5)
    assert await _lots(db, product_id, shop) == ({"OLD": 4.0, "NEW": 3.0}, 7.0)  # nothing moved

    await record_stock_loss(db, company_id, shop, product_id, 4, "EXPIRACAO")  # FEFO: the expired lot first
    assert await _lots(db, product_id, shop) == ({"NEW": 3.0}, 3.0)
    await _sell(db, ctx, product_id, 3)
    assert await _lots(db, product_id, shop) == ({}, 0.0)


@pytest.mark.asyncio
async def test_lots_travel_with_a_transfer_and_come_back_with_a_credit_note(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, central, shop = ctx["company"].id, ctx["central_warehouse"].id, ctx["activity_warehouse"].id
    product_id = await _product(db, ctx)
    await receive_stock(db, company_id, product_id, 5, lot_number="L1", expiry_date=TODAY + timedelta(days=10))
    await receive_stock(db, company_id, product_id, 5, lot_number="L2", expiry_date=TODAY + timedelta(days=30))

    await transfer_stock(db, company_id, product_id, central, shop, 7)
    assert await _lots(db, product_id, central) == ({"L2": 3.0}, 3.0)
    assert await _lots(db, product_id, shop) == ({"L1": 5.0, "L2": 2.0}, 7.0)
    # a chosen lot: taken whatever FEFO would say
    await transfer_stock(db, company_id, product_id, shop, central, 2, lot_id=(await db.execute(select(StockLot.id).where(
        StockLot.warehouse_id == shop, StockLot.lot_number == "L2"))).scalar_one())
    assert await _lots(db, product_id, shop) == ({"L1": 5.0}, 5.0)

    invoice = await _sell(db, ctx, product_id, 3)
    assert await _lots(db, product_id, shop) == ({"L1": 2.0}, 2.0)
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == invoice.id))).scalar_one()
    await create_credit_note(db, company_id, ctx["activity"].id, reference_invoice_id=invoice.id, credit_note_reason="ANL",
                             credit_note_cause="Devolvido", lines_input=[{"invoice_line_id": line_id, "quantity": 3}],
                             restock=True)
    assert await _lots(db, product_id, shop) == ({"L1": 5.0}, 5.0)  # back into the lot the sale took


@pytest.mark.asyncio
async def test_a_cancelled_purchase_takes_back_its_own_lot(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id, central = ctx["company"].id, ctx["gestor"].id, ctx["central_warehouse"].id
    product_id = await _product(db, ctx)
    supplier_id, rate_id = await _purchase_setup(db, ctx)
    first = await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/10", TODAY,
                                            [_line(product_id, rate_id, 6, lot="LATE", days=60)],
                                            stock_entry=True, warehouse_id=central)
    await register_purchase_invoice(db, company_id, user_id, supplier_id, "FT L/11", TODAY,
                                    [_line(product_id, rate_id, 4, lot="SOON", days=5)], stock_entry=True, warehouse_id=central)
    await cancel_purchase_invoice(db, company_id, first.id, user_id, "Erro de registo")
    assert await _lots(db, product_id, central) == ({"SOON": 4.0}, 4.0)  # not FEFO: its own lot


@pytest.mark.asyncio
async def test_a_negative_warehouse_fills_its_gap_before_the_lot(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, shop = ctx["company"].id, ctx["activity_warehouse"].id
    ctx["activity_warehouse"].allow_negative_stock = True
    await db.commit()
    product_id = await _product(db, ctx, expiry=False, name="Pão")
    await _sell(db, ctx, product_id, 4)
    assert await _lots(db, product_id, shop) == ({}, -4.0)
    await receive_stock(db, company_id, product_id, 10, lot_number="P1", warehouse_id=shop)
    assert await _lots(db, product_id, shop) == ({"P1": 6.0}, 6.0)


@pytest.mark.asyncio
async def test_an_adjustment_and_a_guide_keep_the_lots(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id, central = ctx["company"].id, ctx["gestor"].id, ctx["central_warehouse"].id
    product_id = await _product(db, ctx, batch=False)  # by expiry only
    await receive_stock(db, company_id, product_id, 10, expiry_date=TODAY + timedelta(days=9))
    with pytest.raises(InsufficientStockError, match="Indique a validade"):
        await adjust_stock(db, company_id, central, product_id, 12, "Contagem")
    await adjust_stock(db, company_id, central, product_id, 12, "Contagem", expiry_date=TODAY + timedelta(days=40))
    await adjust_stock(db, company_id, central, product_id, 9, "Contagem")  # FEFO: the nearest date
    lots = (await db.execute(select(StockLot.expiry_date, StockLot.quantity).where(
        StockLot.product_id == product_id, StockLot.quantity > 0).order_by(StockLot.expiry_date))).all()
    assert [(d - TODAY).days for d, _ in lots] == [9, 40] and [float(q) for _, q in lots] == [7.0, 2.0]

    if (await db.execute(select(DocumentType).where(DocumentType.code == "GR"))).scalar_one_or_none() is None:
        db.add(DocumentType(code="GR", name="Guia de Remessa", area="FACTURACAO", is_fiscal=True, saft_section="MOVEMENTS"))
    customer = Customer(company_id=company_id, name="Hotel Kilamba", nif="5000222333",
                        legal_person_type=LegalPersonType.JURIDICA, address="Rua 1")
    db.add(customer)
    await db.commit()
    guide = await create_goods_movement(db, company_id, user_id, "GR", central, [{"product_id": product_id, "quantity": 8}],
                                        customer_id=customer.id)
    remaining = (await db.execute(select(StockLot.quantity).where(StockLot.product_id == product_id, StockLot.quantity > 0))).scalars().all()
    assert [float(q) for q in remaining] == [1.0]
    await cancel_goods_movement(db, company_id, guide.id, user_id, "Recusado")
    lots = (await db.execute(select(StockLot.expiry_date, StockLot.quantity).where(
        StockLot.product_id == product_id, StockLot.quantity > 0).order_by(StockLot.expiry_date))).all()
    assert [float(q) for _, q in lots] == [7.0, 2.0]  # back into the lots it took


@pytest.mark.asyncio
async def test_a_production_makes_its_own_lot(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, shop = ctx["company"].id, ctx["activity_warehouse"].id
    flour = Product(company_id=company_id, code="MP-" + uuid.uuid4().hex[:4], name="Farinha", vat_id=None, price=0,
                    min_stock_threshold=0, product_type=ProductType.BEM, is_raw_material=True,
                    unit_of_measure_id=ctx["unit_un"].id)
    db.add(flour)
    await db.flush()
    db.add(Stock(company_id=company_id, product_id=flour.id, warehouse_id=shop, quantity=40))
    await db.commit()
    bread_id = await _product(db, ctx, name="Bolo")
    await set_recipe(db, company_id, bread_id, 10, [{"ingredient_product_id": flour.id, "quantity_per_batch": 5}])
    with pytest.raises(InsufficientStockError, match="Indique a validade de Bolo"):
        await produce_stock(db, company_id, shop, bread_id, 10)
    await db.rollback()
    await produce_stock(db, company_id, shop, bread_id, 10, expiry_date=TODAY + timedelta(days=3))
    assert await _lots(db, bread_id, shop) == ({f"P{TODAY:%Y%m%d}": 10.0}, 10.0)


@pytest.mark.asyncio
async def test_following_by_lot_changes_only_with_the_stock_at_zero(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, central = ctx["company"].id, ctx["central_warehouse"].id
    product_id = await _product(db, ctx, batch=False, expiry=False, name="Sumo")
    await receive_stock(db, company_id, product_id, 5)
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    with pytest.raises(LotTrackingLockedError, match="stock a zero"):
        await ensure_lot_tracking_can_change(db, product, True, False, True)
    await ensure_lot_tracking_can_change(db, product, False, False, True)  # nothing changes: allowed
    await adjust_stock(db, company_id, central, product_id, 0, "Zerar")
    await ensure_lot_tracking_can_change(db, product, True, False, True)
