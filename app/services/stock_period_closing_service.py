"""
Fecho de stock por período (point 11) - an option of the company (Company.stock_period_closing), set by the GESTOR.

For a fiscal period, per product and warehouse: the stock at its start, what came in and went out during it, the stock
at its end and its value at the average cost of that time. Always computed from the stock ledger (StockMovement, every
row booked in a period); when the period is closed for good (FECHADO) with the option on, the figures are frozen
(StockPeriodClosing) and read from there ever after. A period not frozen (still open, or closed while the option was
off) is computed on demand.

The average cost of a period's end is the cost after the last entry booked up to that period (the history of the
cost); a product without such an entry takes its current average cost.
"""
import uuid
from datetime import date

from sqlalchemy import and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.product import Product
from app.models.stock_movement import StockMovement
from app.models.stock_period_closing import StockPeriodClosing
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.warehouse import Warehouse
from app.services.fiscal_period_service import MONTH_NAMES_PT
from app.services.stock_service import ledger_signed_quantity


class StockClosingPeriodNotFoundError(Exception):
    pass


async def _period(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> tuple[FiscalPeriod, int]:
    row = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalPeriod.company_id == company_id)
    )).first()
    if row is None:
        raise StockClosingPeriodNotFoundError("Período fiscal inválido")
    return row[0], row[1]


def _bounds(year: int, month: int):
    """(rows booked before the period, rows booked in it) - a row without a period counts by its creation date."""
    start = date(year, month, 1)
    end = date(year + (1 if month == 12 else 0), month % 12 + 1, 1)
    no_period = StockMovement.fiscal_period_id.is_(None)
    before = or_(
        and_(no_period, StockMovement.created_at < start),
        FiscalYear.year < year,
        and_(FiscalYear.year == year, FiscalPeriod.month < month),
    )
    within = or_(
        and_(no_period, StockMovement.created_at >= start, StockMovement.created_at < end),
        and_(FiscalYear.year == year, FiscalPeriod.month == month),
    )
    return before, within


async def compute_period_stock(db: AsyncSession, company_id: uuid.UUID, period: FiscalPeriod, year: int) -> list[dict]:
    """[{product_id, warehouse_id, opening, in, out, closing, unit_cost, value}] from the ledger - every product and
    warehouse that had stock or movements up to the end of the period."""
    signed = ledger_signed_quantity()
    before, within = _bounds(year, period.month)
    rows = (await db.execute(
        select(
            StockMovement.product_id, StockMovement.warehouse_id,
            func.coalesce(func.sum(case((before, signed), else_=0)), 0),
            func.coalesce(func.sum(case((and_(within, signed > 0), signed), else_=0)), 0),
            func.coalesce(func.sum(case((and_(within, signed < 0), -signed), else_=0)), 0),
        )
        .select_from(StockMovement)
        .outerjoin(FiscalPeriod, FiscalPeriod.id == StockMovement.fiscal_period_id)
        .outerjoin(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(StockMovement.company_id == company_id, or_(before, within))
        .group_by(StockMovement.product_id, StockMovement.warehouse_id)
    )).all()

    # the average cost at the end of the period: after the last entry booked up to it, else the current one
    last_costs = {}
    for product_id, cost in (await db.execute(
        select(StockMovement.product_id, StockMovement.average_cost_after)
        .select_from(StockMovement)
        .outerjoin(FiscalPeriod, FiscalPeriod.id == StockMovement.fiscal_period_id)
        .outerjoin(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(StockMovement.company_id == company_id, StockMovement.average_cost_after.is_not(None),
               or_(*_bounds(year, period.month)))
        .order_by(StockMovement.created_at)
    )).all():
        last_costs[product_id] = float(cost)  # ordered by time: the last one wins
    current_costs = dict((await db.execute(
        select(Product.id, Product.average_cost).where(Product.company_id == company_id)
    )).all())

    result = []
    for product_id, warehouse_id, opening, entered, left in rows:
        opening, entered, left = float(opening), float(entered), float(left)
        closing = round(opening + entered - left, 3)
        if not any((opening, entered, left, closing)):
            continue
        cost = last_costs.get(product_id)
        if cost is None and current_costs.get(product_id) is not None:
            cost = float(current_costs[product_id])
        result.append({
            "product_id": product_id, "warehouse_id": warehouse_id,
            "opening": round(opening, 3), "in": round(entered, 3), "out": round(left, 3), "closing": closing,
            "unit_cost": round(cost, 4) if cost is not None else None,
            # an empty stock is worth nothing, known cost or not
            "value": round(closing * cost, 2) if cost is not None else (0.0 if closing == 0 else None),
        })
    return result


async def quantity_at_period_end(
    db: AsyncSession, company_id: uuid.UUID, period: FiscalPeriod, year: int, product_id: uuid.UUID, warehouse_id: uuid.UUID,
) -> float:
    """The stock of one product in one warehouse at the end of a period - every ledger row booked up to it."""
    before, within = _bounds(year, period.month)
    total = (await db.execute(
        select(func.coalesce(func.sum(ledger_signed_quantity()), 0))
        .select_from(StockMovement)
        .outerjoin(FiscalPeriod, FiscalPeriod.id == StockMovement.fiscal_period_id)
        .outerjoin(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(StockMovement.company_id == company_id, StockMovement.product_id == product_id,
               StockMovement.warehouse_id == warehouse_id, or_(before, within))
    )).scalar_one()
    return float(total)


async def freeze_period_stock(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> int:
    """Freezes the stock of a period closed for good, when the company has the option - once (an already frozen period
    is kept as it is). No commit: part of the closing's transaction. Returns the number of rows written."""
    enabled = (await db.execute(select(Company.stock_period_closing).where(Company.id == company_id))).scalar_one()
    if not enabled:
        return 0
    already = (await db.execute(
        select(func.count()).select_from(StockPeriodClosing).where(StockPeriodClosing.fiscal_period_id == period_id)
    )).scalar_one()
    if already:
        return 0
    period, year = await _period(db, company_id, period_id)
    rows = await compute_period_stock(db, company_id, period, year)
    for r in rows:
        db.add(StockPeriodClosing(
            company_id=company_id, fiscal_period_id=period_id, product_id=r["product_id"], warehouse_id=r["warehouse_id"],
            opening_quantity=r["opening"], in_quantity=r["in"], out_quantity=r["out"], closing_quantity=r["closing"],
            unit_cost=r["unit_cost"], closing_value=r["value"],
        ))
    return len(rows)


async def get_period_stock_report(
    db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID, warehouse_id: uuid.UUID | None = None,
) -> dict:
    """{period_label, period_status, frozen, frozen_at, lines: [...], totals} - the frozen figures when the period was
    frozen, else computed now from the ledger."""
    period, year = await _period(db, company_id, period_id)
    frozen_rows = (await db.execute(
        select(StockPeriodClosing).where(StockPeriodClosing.company_id == company_id,
                                         StockPeriodClosing.fiscal_period_id == period_id)
    )).scalars().all()
    if frozen_rows:
        rows = [{
            "product_id": r.product_id, "warehouse_id": r.warehouse_id,
            "opening": float(r.opening_quantity), "in": float(r.in_quantity), "out": float(r.out_quantity),
            "closing": float(r.closing_quantity),
            "unit_cost": float(r.unit_cost) if r.unit_cost is not None else None,
            "value": float(r.closing_value) if r.closing_value is not None else None,
        } for r in frozen_rows]
        frozen_at = max(r.created_at for r in frozen_rows)
    else:
        rows = await compute_period_stock(db, company_id, period, year)
        frozen_at = None
    if warehouse_id is not None:
        rows = [r for r in rows if r["warehouse_id"] == warehouse_id]

    products = {p.id: p for p in (await db.execute(
        select(Product).where(Product.id.in_({r["product_id"] for r in rows}))
    )).scalars().all()} if rows else {}
    warehouses = dict((await db.execute(
        select(Warehouse.id, Warehouse.name).where(Warehouse.company_id == company_id)
    )).all())
    units = dict((await db.execute(select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code))).all())

    lines = []
    for r in rows:
        product = products.get(r["product_id"])
        lines.append({
            **r,
            "code": product.code if product else "-", "name": product.name if product else "-",
            "unit_code": units.get(product.unit_of_measure_id) if product else None,
            "is_raw_material": bool(product and product.is_raw_material),
            "warehouse_name": warehouses.get(r["warehouse_id"], "-"),
        })
    lines.sort(key=lambda l: (l["name"], l["warehouse_name"]))
    return {
        "period_label": f"{MONTH_NAMES_PT[period.month]} {year}",
        "period_status": getattr(period.status, "value", period.status),
        "frozen": bool(frozen_rows), "frozen_at": frozen_at,
        "lines": lines,
        "totals": {
            "value": round(sum(l["value"] for l in lines if l["value"] is not None), 2),
            "cost_unknown": sum(1 for l in lines if l["value"] is None),
        },
    }
