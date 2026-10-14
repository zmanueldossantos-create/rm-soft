"""Point 11 (Inventário): count a warehouse - a draft lists the products managed by stock with their expected stock,
the counts are saved, and the validation turns each difference into an adjustment, freezing the document. An
uncounted line changes nothing; a validated inventory never changes."""
import io

import pytest
from sqlalchemy import select

from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.stock_movement import MovementType, StockMovement
from app.services.stock_inventory_service import (
    InventoryStateError, create_inventory, get_inventory, list_inventories, save_counts, validate_inventory,
)
from app.services.stock_service import receive_stock
from app.utils.inventory_pdf import generate_inventory_pdf


async def _shop(db, ctx):
    company_id = ctx["company"].id
    flour = Product(company_id=company_id, code="INV-FAR", name="Farinha", vat_id=None, price=0, min_stock_threshold=0,
                    product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=ctx["unit_un"].id, average_cost=1000)
    sugar = Product(company_id=company_id, code="INV-ACU", name="Açúcar", vat_id=None, price=0, min_stock_threshold=0,
                    product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=ctx["unit_un"].id, average_cost=500)
    db.add_all([flour, sugar])
    await db.commit()
    await receive_stock(db, company_id, flour.id, 40)
    await receive_stock(db, company_id, sugar.id, 10)
    warehouse = (await db.execute(select(Stock.warehouse_id).where(Stock.product_id == flour.id))).scalar_one()
    return flour, sugar, warehouse


@pytest.mark.asyncio
async def test_an_inventory_books_its_differences_and_freezes(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    flour, sugar, warehouse_id = await _shop(db, ctx)
    inventory = await create_inventory(db, company_id, warehouse_id, user_id)
    draft = await get_inventory(db, company_id, inventory.id)
    lines = {l["code"]: l for l in draft["lines"]}
    assert (lines["INV-FAR"]["expected"], lines["INV-ACU"]["expected"]) == (40.0, 10.0)
    assert draft["reference"].startswith("INV") and draft["status"] == "RASCUNHO"

    with pytest.raises(InventoryStateError, match="já tem um inventário em curso"):
        await create_inventory(db, company_id, warehouse_id, user_id)

    await save_counts(db, company_id, inventory.id, [
        {"product_id": flour.id, "counted_quantity": 37, "count_detail": "37 UN"},  # 3 missing
        {"product_id": sugar.id, "counted_quantity": None},                          # not counted
    ])
    done = await validate_inventory(db, company_id, inventory.id, user_id)
    lines = {l["code"]: l for l in done["lines"]}
    assert (lines["INV-FAR"]["difference"], lines["INV-FAR"]["difference_value"]) == (-3.0, -3000.0)
    assert lines["INV-ACU"]["counted"] is None and lines["INV-ACU"]["difference"] is None
    assert done["summary"] == {"lines": len(done["lines"]), "counted": 1, "differences": 1, "difference_value": -3000.0}

    stock = {pid: float(q) for pid, q in (await db.execute(
        select(Stock.product_id, Stock.quantity).where(Stock.warehouse_id == warehouse_id))).all()}
    assert (stock[flour.id], stock[sugar.id]) == (37.0, 10.0)
    adjustment = (await db.execute(select(StockMovement).where(
        StockMovement.product_id == flour.id, StockMovement.movement_type == MovementType.AJUSTE))).scalar_one()
    assert (float(adjustment.quantity), adjustment.reference) == (-3.0, done["reference"])

    with pytest.raises(InventoryStateError, match="validado"):
        await save_counts(db, company_id, inventory.id, [{"product_id": flour.id, "counted_quantity": 1}])
    listed = await list_inventories(db, company_id, warehouse_id)
    assert [(i["reference"], i["status"], i["summary"]["differences"]) for i in listed] == [(done["reference"], "VALIDADO", 1)]

    pypdf = pytest.importorskip("pypdf")
    text = " ".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(generate_inventory_pdf(done, {"name": "X", "nif": "1"}))).pages)
    assert "INVENTÁRIO" in text and "Farinha" in text


@pytest.mark.asyncio
async def test_an_inventory_without_any_count_is_not_validated(db, company_with_essentials):
    ctx = company_with_essentials
    flour, _, warehouse_id = await _shop(db, ctx)
    inventory = await create_inventory(db, ctx["company"].id, warehouse_id, ctx["gestor"].id)
    with pytest.raises(InventoryStateError, match="Nenhum produto foi contado"):
        await validate_inventory(db, ctx["company"].id, inventory.id, ctx["gestor"].id)


@pytest.mark.asyncio
async def test_with_the_option_a_period_closes_only_after_its_inventories(db, company_with_essentials):
    from app.models.fiscal_period import FiscalPeriod
    from app.services.fiscal_period_service import InvalidFiscalOperationError, close_fiscal_period
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    flour, _, warehouse_id = await _shop(db, ctx)
    flour_id = flour.id  # read before the rollback expires it
    ctx["company"].inventory_before_close = True
    await db.commit()
    period_id = (await db.execute(select(FiscalPeriod.id).where(FiscalPeriod.company_id == company_id,
                                                                FiscalPeriod.status == "ABERTO"))).scalar_one()
    with pytest.raises(InvalidFiscalOperationError, match="inventário validado em cada armazém com stock"):
        await close_fiscal_period(db, company_id, period_id)
    await db.rollback()

    inventory = await create_inventory(db, company_id, warehouse_id, user_id)
    await save_counts(db, company_id, inventory.id, [{"product_id": flour_id, "counted_quantity": 40}])
    await validate_inventory(db, company_id, inventory.id, user_id)
    closed = await close_fiscal_period(db, company_id, period_id)
    assert closed.status == "FECHADO"
