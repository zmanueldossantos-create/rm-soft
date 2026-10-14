"""
Inventário (point 11) - the count of a warehouse's stock, document by document (see StockInventory).

- create: a draft for one warehouse, booked in the chosen period (active, or the soft-closed one for the inventory
  of the month just ended - resolve_posting_period), with one line per product managed by stock. One draft per
  warehouse at a time. Numbered INV<year>/<n> in its period's year.
- the expected quantity of a draft is always live: the stock at the end of its period when that period is
  soft-closed, else the warehouse's current stock.
- save: the counted quantities (base unit, with the count as typed: "1 SC + 17 KG"); None leaves a line uncounted.
- validate: every counted line that differs becomes an adjustment (AJUSTE, reference = the inventory), applied to the
  warehouse's stock; each line's expected quantity, difference and value at the average cost are frozen.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fiscal_year import FiscalYear
from app.models.product import Product, ProductType
from app.models.product_sale_unit import ProductSaleUnit
from app.models.stock import Stock
from app.models.stock_inventory import InventoryStatus, StockInventory, StockInventoryLine
from app.models.stock_movement import MovementType, StockMovement
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.user import User
from app.models.warehouse import Warehouse
from app.services.fiscal_period_service import MONTH_NAMES_PT, resolve_posting_period
from app.services.stock_service import _get_or_create_stock_row, get_warehouse_or_raise


class InventoryNotFoundError(Exception):
    pass


class InventoryStateError(Exception):
    """A validated inventory never changes; a warehouse has one draft at a time."""


def _ref(inventory: StockInventory) -> str:
    return f"{inventory.series}/{inventory.number}"


async def _get(db: AsyncSession, company_id: uuid.UUID, inventory_id: uuid.UUID) -> StockInventory:
    inventory = (await db.execute(
        select(StockInventory).where(StockInventory.id == inventory_id, StockInventory.company_id == company_id)
    )).scalar_one_or_none()
    if inventory is None:
        raise InventoryNotFoundError("Inventário não encontrado")
    return inventory


async def _period_and_year(db: AsyncSession, period_id: uuid.UUID):
    from app.models.fiscal_period import FiscalPeriod
    return (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id)
    )).one()


async def _expected(db: AsyncSession, inventory: StockInventory, product_ids) -> dict:
    """{product_id: expected quantity} - at the end of a soft-closed period, else the warehouse's stock now."""
    period, year = await _period_and_year(db, inventory.fiscal_period_id)
    if getattr(period.status, "value", period.status) == "FECHO_PARCIAL":
        from app.services.stock_period_closing_service import quantity_at_period_end
        return {pid: await quantity_at_period_end(db, inventory.company_id, period, year, pid, inventory.warehouse_id)
                for pid in product_ids}
    rows = (await db.execute(
        select(Stock.product_id, Stock.quantity).where(Stock.warehouse_id == inventory.warehouse_id,
                                                       Stock.product_id.in_(list(product_ids)))
    )).all() if product_ids else []
    current = {pid: float(q) for pid, q in rows}
    return {pid: current.get(pid, 0.0) for pid in product_ids}


async def create_inventory(
    db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID, user_id: uuid.UUID,
    fiscal_period_id: uuid.UUID | None = None, description: str | None = None,
) -> StockInventory:
    await get_warehouse_or_raise(db, company_id, warehouse_id)
    draft = (await db.execute(
        select(StockInventory).where(StockInventory.company_id == company_id, StockInventory.warehouse_id == warehouse_id,
                                     StockInventory.status == InventoryStatus.RASCUNHO)
    )).scalars().first()
    if draft is not None:
        raise InventoryStateError(f"Este armazém já tem um inventário em curso ({_ref(draft)}) - termine-o primeiro")
    period = await resolve_posting_period(db, company_id, fiscal_period_id)
    _, year = await _period_and_year(db, period.id)
    series = f"INV{year}"
    last = (await db.execute(
        select(func.max(StockInventory.number)).where(StockInventory.company_id == company_id, StockInventory.series == series)
    )).scalar_one()
    inventory = StockInventory(
        company_id=company_id, warehouse_id=warehouse_id, fiscal_period_id=period.id, series=series,
        number=(last or 0) + 1, status=InventoryStatus.RASCUNHO, description=description, created_by_user_id=user_id,
    )
    db.add(inventory)
    await db.flush()
    # every product managed by stock, and anything that has stock in this warehouse
    stocked = select(Stock.product_id).where(Stock.warehouse_id == warehouse_id, Stock.quantity != 0)
    product_ids = (await db.execute(
        select(Product.id).where(
            Product.company_id == company_id, Product.product_type == ProductType.BEM, Product.managed_by_stock.is_(True),
            (Product.is_active.is_(True)) | (Product.id.in_(stocked)),
        )
    )).scalars().all()
    for product_id in product_ids:
        db.add(StockInventoryLine(inventory_id=inventory.id, product_id=product_id))
    await db.commit()
    await db.refresh(inventory)
    return inventory


async def get_inventory(db: AsyncSession, company_id: uuid.UUID, inventory_id: uuid.UUID) -> dict:
    """The inventory with its lines (expected live for a draft, frozen once validated), sorted by product name."""
    inventory = await _get(db, company_id, inventory_id)
    lines = (await db.execute(
        select(StockInventoryLine, Product).join(Product, Product.id == StockInventoryLine.product_id)
        .where(StockInventoryLine.inventory_id == inventory.id)
    )).all()
    validated = inventory.status == InventoryStatus.VALIDADO
    expected = {} if validated else await _expected(db, inventory, [p.id for _, p in lines])
    units = dict((await db.execute(select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code))).all())
    sale_units: dict = {}
    for unit in (await db.execute(
        select(ProductSaleUnit).where(ProductSaleUnit.product_id.in_([p.id for _, p in lines]), ProductSaleUnit.is_active.is_(True))
    )).scalars().all() if lines else []:
        sale_units.setdefault(unit.product_id, []).append(
            {"id": unit.id, "code": units.get(unit.unit_of_measure_id), "factor": float(unit.factor)})
    period, year = await _period_and_year(db, inventory.fiscal_period_id)
    warehouse = (await db.execute(select(Warehouse.name).where(Warehouse.id == inventory.warehouse_id))).scalar_one()
    names = dict((await db.execute(
        select(User.id, User.full_name).where(User.id.in_([u for u in (inventory.created_by_user_id, inventory.validated_by_user_id) if u]))
    )).all())

    out = []
    for line, product in lines:
        cost = float(line.unit_cost) if validated and line.unit_cost is not None else (
            float(product.average_cost) if product.average_cost is not None else None)
        exp = float(line.expected_quantity) if validated else round(expected.get(product.id, 0.0), 3)
        counted = float(line.counted_quantity) if line.counted_quantity is not None else None
        diff = (float(line.difference) if validated and line.difference is not None
                else (round(counted - exp, 3) if counted is not None else None))
        value = (float(line.difference_value) if validated and line.difference_value is not None
                 else (round(diff * cost, 2) if diff is not None and cost is not None else None))
        out.append({
            "line_id": line.id, "product_id": product.id, "code": product.code, "name": product.name,
            "is_raw_material": product.is_raw_material, "unit_code": units.get(product.unit_of_measure_id),
            "sale_units": sorted(sale_units.get(product.id, []), key=lambda u: -u["factor"]),
            "expected": exp, "counted": counted, "count_detail": line.count_detail,
            "difference": diff, "unit_cost": cost, "difference_value": value,
        })
    out.sort(key=lambda l: l["name"])
    differing = [l for l in out if l["difference"] not in (None, 0)]
    return {
        "id": inventory.id, "reference": _ref(inventory), "status": inventory.status.value,
        "warehouse_id": inventory.warehouse_id, "warehouse_name": warehouse,
        "fiscal_period_id": inventory.fiscal_period_id, "period_label": f"{MONTH_NAMES_PT[period.month]} {year}",
        "period_status": getattr(period.status, "value", period.status),
        "description": inventory.description,
        "created_at": inventory.created_at, "created_by": names.get(inventory.created_by_user_id),
        "validated_at": inventory.validated_at, "validated_by": names.get(inventory.validated_by_user_id),
        "lines": out,
        "summary": {
            "lines": len(out), "counted": sum(1 for l in out if l["counted"] is not None), "differences": len(differing),
            "difference_value": round(sum(l["difference_value"] or 0 for l in differing), 2),
        },
    }


async def save_counts(db: AsyncSession, company_id: uuid.UUID, inventory_id: uuid.UUID, counts: list[dict]) -> None:
    """counts: [{product_id, counted_quantity (base unit, None = uncounted), count_detail}] - a draft only."""
    inventory = await _get(db, company_id, inventory_id)
    if inventory.status != InventoryStatus.RASCUNHO:
        raise InventoryStateError("Este inventário já foi validado e não pode ser alterado")
    lines = {l.product_id: l for l in (await db.execute(
        select(StockInventoryLine).where(StockInventoryLine.inventory_id == inventory.id)
    )).scalars().all()}
    for count in counts:
        line = lines.get(count["product_id"])
        if line is None:
            continue
        quantity = count.get("counted_quantity")
        if quantity is not None and float(quantity) < 0:
            raise InventoryStateError("Uma quantidade contada não pode ser negativa")
        line.counted_quantity = None if quantity is None else round(float(quantity), 3)
        line.count_detail = (count.get("count_detail") or None) if quantity is not None else None
    await db.commit()


async def validate_inventory(db: AsyncSession, company_id: uuid.UUID, inventory_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    """Books the differences as adjustments and freezes the document. Refused without any counted line, or when its
    period no longer takes entries (closed for good meanwhile)."""
    inventory = await _get(db, company_id, inventory_id)
    if inventory.status != InventoryStatus.RASCUNHO:
        raise InventoryStateError("Este inventário já foi validado")
    period = await resolve_posting_period(db, company_id, inventory.fiscal_period_id)  # refuses a closed period
    lines = (await db.execute(
        select(StockInventoryLine, Product).join(Product, Product.id == StockInventoryLine.product_id)
        .where(StockInventoryLine.inventory_id == inventory.id)
    )).all()
    if not any(line.counted_quantity is not None for line, _ in lines):
        raise InventoryStateError("Nenhum produto foi contado - conte pelo menos um antes de validar")
    expected = await _expected(db, inventory, [p.id for _, p in lines])
    reference = _ref(inventory)
    for line, product in lines:
        exp = round(expected.get(product.id, 0.0), 3)
        line.expected_quantity = exp
        if line.counted_quantity is None:
            continue
        diff = round(float(line.counted_quantity) - exp, 3)
        cost = float(product.average_cost) if product.average_cost is not None else None
        line.difference, line.unit_cost = diff, cost
        line.difference_value = round(diff * cost, 2) if cost is not None else None
        if diff == 0:
            continue
        stock = await _get_or_create_stock_row(db, company_id, product.id, inventory.warehouse_id)
        stock.quantity = float(stock.quantity) + diff
        db.add(StockMovement(
            company_id=company_id, fiscal_period_id=period.id, product_id=product.id, warehouse_id=inventory.warehouse_id,
            movement_type=MovementType.AJUSTE, quantity=diff, reference=reference,  # signed, as every AJUSTE
            reason=f"Inventário {reference}",
        ))
    inventory.status = InventoryStatus.VALIDADO
    inventory.validated_by_user_id = user_id
    inventory.validated_at = datetime.now(timezone.utc)
    await db.commit()
    return await get_inventory(db, company_id, inventory.id)


class InventoryMissingError(Exception):
    """A period cannot be closed for good before every warehouse holding stock has its validated inventory."""


async def ensure_inventories_before_close(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> None:
    """Inventário obrigatório antes do fecho (company option): every active warehouse with stock at the end of the
    period needs a VALIDATED inventory booked in that period. Raises InventoryMissingError naming the warehouses."""
    from app.models.company import Company
    from app.services.stock_period_closing_service import compute_period_stock
    if not (await db.execute(select(Company.inventory_before_close).where(Company.id == company_id))).scalar_one():
        return
    period, year = await _period_and_year(db, period_id)
    holding = {r["warehouse_id"] for r in await compute_period_stock(db, company_id, period, year) if r["closing"] != 0}
    if not holding:
        return
    done = set((await db.execute(
        select(StockInventory.warehouse_id).where(StockInventory.company_id == company_id,
                                                  StockInventory.fiscal_period_id == period_id,
                                                  StockInventory.status == InventoryStatus.VALIDADO)
    )).scalars().all())
    missing = holding - done
    if not missing:
        return
    names = sorted((await db.execute(
        select(Warehouse.name).where(Warehouse.id.in_(missing), Warehouse.is_active.is_(True))
    )).scalars().all())
    if names:
        raise InventoryMissingError(
            f"O período de {MONTH_NAMES_PT[period.month]} de {year} só pode ser fechado definitivamente depois de um "
            f"inventário validado em cada armazém com stock. Falta: {', '.join(names)}"
        )


async def list_inventories(db: AsyncSession, company_id: uuid.UUID, warehouse_id: uuid.UUID | None = None) -> list[dict]:
    """The inventories, most recent first, with their counts and the value of their differences."""
    query = select(StockInventory).where(StockInventory.company_id == company_id)
    if warehouse_id is not None:
        query = query.where(StockInventory.warehouse_id == warehouse_id)
    inventories = (await db.execute(query.order_by(StockInventory.created_at.desc()))).scalars().all()
    result = []
    for inventory in inventories:
        detail = await get_inventory(db, company_id, inventory.id)
        result.append({k: detail[k] for k in ("id", "reference", "status", "warehouse_id", "warehouse_name", "period_label",
                                              "description", "created_at", "created_by", "validated_at", "validated_by",
                                              "summary")})
    return result
