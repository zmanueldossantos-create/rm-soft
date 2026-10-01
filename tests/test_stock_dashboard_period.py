"""The stock summary at the end of a fiscal period is summed from the ledger; without a period it is the current stock."""
import pytest

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.product import Product, ProductType
from app.models.stock import Stock
from app.services.stock_service import adjust_stock, get_stock_dashboard


@pytest.mark.asyncio
async def test_the_summary_of_an_earlier_period_reads_the_ledger(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, warehouse_id = ctx["company"].id, ctx["activity_warehouse"].id
    product = Product(company_id=company_id, code="DB-01", name="Produto resumo", vat_id=ctx["vat_nor"].id, price=100.0,
                      min_stock_threshold=0, product_type=ProductType.BEM)
    year = FiscalYear(company_id=company_id, year=2020, status="FECHO_PARCIAL")
    db.add_all([product, year])
    await db.commit()
    await db.refresh(product)
    await db.refresh(year)
    earlier = FiscalPeriod(company_id=company_id, fiscal_year_id=year.id, month=9, status="FECHO_PARCIAL")
    db.add_all([earlier, Stock(company_id=company_id, product_id=product.id, warehouse_id=warehouse_id, quantity=0)])
    await db.commit()
    await db.refresh(earlier)

    await adjust_stock(db, company_id, warehouse_id, product.id, 10, "Contagem antiga", fiscal_period_id=earlier.id)
    await adjust_stock(db, company_id, warehouse_id, product.id, 15, "Contagem atual")

    def quantity_of(summary):
        return next(i["total_quantity"] for i in summary["items"] if i["product_id"] == product.id)

    assert quantity_of(await get_stock_dashboard(db, company_id, earlier.id)) == 10.0
    assert quantity_of(await get_stock_dashboard(db, company_id)) == 15.0
