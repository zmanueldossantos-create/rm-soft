"""Point 11 (Fecho de stock por período, a company option): the stock of a period per product and warehouse - start,
in, out, end and value - frozen when the period is closed for good with the option on, computed from the ledger
otherwise. A late entry booked in the soft-closed month counts in that month."""
import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.product import Product, ProductType
from app.models.stock_period_closing import StockPeriodClosing
from app.services.fiscal_period_service import close_fiscal_period
from app.services.stock_period_closing_service import get_period_stock_report
from app.services.stock_service import get_default_warehouse, receive_stock, record_stock_loss


async def _september_and_october(db, ctx, option):
    """Our own year: September soft-closed, October open (the fixture's periods closed); a product costing 10."""
    company = ctx["company"]
    for period in (await db.execute(select(FiscalPeriod).where(FiscalPeriod.company_id == company.id))).scalars():
        period.status = "FECHADO"
    for year in (await db.execute(select(FiscalYear).where(FiscalYear.company_id == company.id))).scalars():
        year.status = "FECHADO"
    fiscal_year = FiscalYear(company_id=company.id, year=2090, status="ABERTO")
    db.add(fiscal_year)
    await db.flush()
    september = FiscalPeriod(company_id=company.id, fiscal_year_id=fiscal_year.id, month=9, status="FECHO_PARCIAL")
    october = FiscalPeriod(company_id=company.id, fiscal_year_id=fiscal_year.id, month=10, status="ABERTO")
    product = Product(company_id=company.id, code="FAR-11", name="Farinha", vat_id=None, price=0, min_stock_threshold=0,
                      product_type=ProductType.BEM, is_raw_material=True, unit_of_measure_id=ctx["unit_un"].id,
                      average_cost=10)
    company.stock_period_closing = option
    db.add_all([september, october, product])
    await db.commit()
    company_id = company.id
    await receive_stock(db, company_id, product.id, 100, fiscal_period_id=september.id)
    await receive_stock(db, company_id, product.id, 50, fiscal_period_id=october.id)
    warehouse = await get_default_warehouse(db, company_id)
    await record_stock_loss(db, company_id, warehouse.id, product.id, 30, "QUEBRA", fiscal_period_id=september.id)  # late
    return september, october, product


def _figures(report):
    return [(l["code"], l["opening"], l["in"], l["out"], l["closing"], l["unit_cost"], l["value"]) for l in report["lines"]]


@pytest.mark.asyncio
async def test_closing_a_period_freezes_its_stock(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    september, october, product = await _september_and_october(db, ctx, option=True)
    await close_fiscal_period(db, company_id, september.id)

    product.average_cost = 20  # the cost moves afterwards: September stays as it was frozen
    await db.commit()
    frozen = await get_period_stock_report(db, company_id, september.id)
    assert frozen["frozen"] is True
    assert _figures(frozen) == [("FAR-11", 0.0, 100.0, 30.0, 70.0, 10.0, 700.0)]
    assert frozen["totals"]["value"] == 700.0

    live = await get_period_stock_report(db, company_id, october.id)  # still open: computed now
    assert live["frozen"] is False
    assert _figures(live) == [("FAR-11", 70.0, 50.0, 0.0, 120.0, 20.0, 2400.0)]


@pytest.mark.asyncio
async def test_without_the_option_nothing_is_frozen(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    september, _, _ = await _september_and_october(db, ctx, option=False)
    await close_fiscal_period(db, company_id, september.id)
    assert (await db.execute(select(StockPeriodClosing))).first() is None
    report = await get_period_stock_report(db, company_id, september.id)
    assert report["frozen"] is False and _figures(report)[0][1:5] == (0.0, 100.0, 30.0, 70.0)


async def _late_loss(db, ctx, option):
    """September soft-closed with 100 in and 30 lost (70 left at its end), October brings 50 more (120 today)."""
    september, october, product = await _september_and_october(db, ctx, option=False)
    ctx["company"].stock_check_at_period_end = option
    await db.commit()
    return september, product, await get_default_warehouse(db, ctx["company"].id)


@pytest.mark.asyncio
async def test_a_late_exit_takes_the_stock_of_its_own_period(db, company_with_essentials):
    from app.services.stock_service import InsufficientStockError
    ctx = company_with_essentials
    company_id = ctx["company"].id
    september, product, warehouse = await _late_loss(db, ctx, option=True)
    ids = (warehouse.id, product.id)  # read before the rollback expires them
    september_id = september.id
    with pytest.raises(InsufficientStockError, match="no fim de Setembro de 2090"):
        await record_stock_loss(db, company_id, *ids, 80, "QUEBRA", fiscal_period_id=september_id)  # 70 at its end
    await db.rollback()
    await record_stock_loss(db, company_id, *ids, 70, "QUEBRA", fiscal_period_id=september_id)


@pytest.mark.asyncio
async def test_without_the_option_a_late_exit_takes_todays_stock(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    september, product, warehouse = await _late_loss(db, ctx, option=False)
    await record_stock_loss(db, company_id, warehouse.id, product.id, 80, "QUEBRA", fiscal_period_id=september.id)
