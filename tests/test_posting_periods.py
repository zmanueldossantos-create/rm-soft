"""Internal entries are booked in a chosen period (active or soft-closed), never in a closed one; sales in the active one."""
import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.models.stock_movement import StockMovement
from app.services.fiscal_period_service import PeriodClosedError
from app.services.stock_service import adjust_stock, deduct_stock_for_sale


async def _setup(db, ctx):
    """A product in stock, the conftest's active period, plus a soft-closed and a closed one in a year of our own."""
    company_id = ctx["company"].id
    product = Product(company_id=company_id, code="PP-01", name="Produto periodo", vat_id=ctx["vat_nor"].id, price=100.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    db.add(product)
    year = FiscalYear(company_id=company_id, year=2090, status="ABERTO")
    db.add(year)
    await db.commit()
    await db.refresh(product)
    await db.refresh(year)
    soft = FiscalPeriod(company_id=company_id, fiscal_year_id=year.id, month=9, status="FECHO_PARCIAL")
    closed = FiscalPeriod(company_id=company_id, fiscal_year_id=year.id, month=8, status="FECHADO")
    db.add_all([soft, closed, Stock(company_id=company_id, product_id=product.id, warehouse_id=ctx["activity_warehouse"].id, quantity=10)])
    await db.commit()
    await db.refresh(soft)
    await db.refresh(closed)
    active = (await db.execute(select(FiscalPeriod).where(FiscalPeriod.company_id == company_id, FiscalPeriod.status == "ABERTO"))).scalar_one()
    return company_id, product.id, ctx["activity_warehouse"].id, active, soft, closed


async def _last_movement_period(db, product_id):
    return (await db.execute(
        select(StockMovement.fiscal_period_id).where(StockMovement.product_id == product_id).order_by(StockMovement.created_at.desc()).limit(1)
    )).scalar_one()


@pytest.mark.asyncio
async def test_an_internal_entry_goes_to_the_active_period_by_default(db, company_with_essentials):
    company_id, product_id, warehouse_id, active, soft, closed = await _setup(db, company_with_essentials)
    await adjust_stock(db, company_id, warehouse_id, product_id, 12, "Contagem")
    assert await _last_movement_period(db, product_id) == active.id


@pytest.mark.asyncio
async def test_a_late_internal_entry_may_go_to_the_soft_closed_period(db, company_with_essentials):
    company_id, product_id, warehouse_id, active, soft, closed = await _setup(db, company_with_essentials)
    await adjust_stock(db, company_id, warehouse_id, product_id, 15, "Contagem tardia", fiscal_period_id=soft.id)
    assert await _last_movement_period(db, product_id) == soft.id


@pytest.mark.asyncio
async def test_a_closed_period_takes_nothing(db, company_with_essentials):
    company_id, product_id, warehouse_id, active, soft, closed = await _setup(db, company_with_essentials)
    with pytest.raises(PeriodClosedError, match="fechado definitivamente"):
        await adjust_stock(db, company_id, warehouse_id, product_id, 15, "Contagem", fiscal_period_id=closed.id)


@pytest.mark.asyncio
async def test_a_sale_is_booked_in_the_active_period(db, company_with_essentials):
    company_id, product_id, warehouse_id, active, soft, closed = await _setup(db, company_with_essentials)
    await deduct_stock_for_sale(db, company_id=company_id, warehouse_id=warehouse_id, product_id=product_id, quantity=1, reference="FT T/1")
    assert await _last_movement_period(db, product_id) == active.id
