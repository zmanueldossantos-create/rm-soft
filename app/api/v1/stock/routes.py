"""
Stock routes - scoped to the caller's company (multi-tenant isolation).
See specification v6/v7, section 5.1.
Multi-warehouse (see stock_service module docstring): goods are received
into the CENTRAL warehouse, then internally transferred between any of
the company's warehouses (central <-> activity, or activity <-> activity)
before being sold or written off (PERDA) at a specific point of sale.
"""
from app.services.stock_service import StockQuantityError
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.stock import (
    StockLevelResponse,
    StockAdjustRequest,
    StockTransferRequest,
    StockLossRequest,
    StockMovementResponse,
)
from app.schemas.recipe import ProduceStockRequest, ProductionEstimateResponse
from app.schemas.warehouse import WarehouseResponse, WarehouseUpdateRequest, WarehouseCreateRequest, WarehouseCreateFullRequest
from app.services.fiscal_period_service import PeriodClosedError
from app.services.stock_service import (
    list_stock_levels,
    list_stock_movements,
    get_movement_periods,
    list_warehouses,
    create_warehouse,
    update_warehouse,
    toggle_warehouse_status,
    CentralWarehouseNotEditableError,
    adjust_stock,
    transfer_stock,
    record_stock_loss,
    produce_stock,
    estimate_production_capacity,
    list_production_history,
    get_stock_dashboard,
    get_default_warehouse,
    rename_warehouse,
    WarehouseNotFoundError,
    InsufficientStockError,
    NoRecipeError,
)

from app.services.stock_period_closing_service import StockClosingPeriodNotFoundError, get_period_stock_report

from app.schemas.stock_inventory import InventoryCountsRequest, InventoryCreateRequest
from app.services.stock_inventory_service import (
    InventoryNotFoundError, InventoryStateError, create_inventory, get_inventory, list_inventories, save_counts,
    validate_inventory,
)

router = APIRouter(prefix="/api/v1/stock", tags=["stock"])



@router.get("/warehouses", response_model=list[WarehouseResponse])
async def get_warehouses(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("warehouses:view")),
):
    """Lists all of the company's warehouses (central + one per activity)."""
    return await list_warehouses(db, current_user.company_id)


@router.post("/warehouses", response_model=WarehouseResponse, status_code=status.HTTP_201_CREATED)
async def post_warehouse(
    payload: WarehouseCreateFullRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("warehouses:create")),
):
    """Creates a new secondary warehouse for the company."""
    return await create_warehouse(
        db, current_user.company_id, payload.name, payload.code, payload.province_id,
        payload.municipality_id, payload.address, payload.allow_negative_stock,
        payload.entradas_bloqueadas, payload.saidas_bloqueadas,
    )


@router.get("/levels", response_model=list[StockLevelResponse])
async def get_stock_levels(
    warehouse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Lists current stock quantity for every product in the given warehouse."""
    return await list_stock_levels(db, current_user.company_id, warehouse_id)


@router.get("/movements", response_model=list[StockMovementResponse])
async def get_stock_movements(
    warehouse_id: uuid.UUID | None = None,
    year: int | None = None,
    month: int | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Lists recent stock movements (audit trail), filtered and paginated."""
    from app.services.stock_lot_service import lots_of_movements
    movements = await list_stock_movements(db, current_user.company_id, warehouse_id, year, month, date_from, date_to, limit, offset)
    lots = await lots_of_movements(db, [m.id for m in movements])  # a product followed by lot: which lots it moved
    return [{**StockMovementResponse.model_validate(m).model_dump(), "lots": lots.get(m.id)} for m in movements]


@router.get("/lots")
async def get_product_lots(
    product_id: uuid.UUID,
    warehouse_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """The lots of a product followed by lot / expiry still holding stock, per warehouse, FEFO (Stock > Lotes)."""
    from app.services.stock_lot_service import list_lots
    return await list_lots(db, current_user.company_id, product_id, warehouse_id)


@router.get("/expiring")
async def get_expiring_lots(
    warehouse_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Stock > Validades: the lots expired or expiring within the company's alert days, every warehouse unless one is given."""
    from app.services.stock_lot_service import list_expiring
    return await list_expiring(db, current_user.company_id, warehouse_id)


@router.get("/movements/available-periods")
async def get_movements_available_periods(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Returns the distinct (year, month) pairs that have stock movements - populates the Ano/Mes filters."""
    return await get_movement_periods(db, current_user.company_id)


@router.post("/transfer", status_code=status.HTTP_204_NO_CONTENT)
async def post_transfer_stock(
    payload: StockTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:transfer")),
):
    """Internally moves stock between any two of the company's warehouses."""
    try:
        await transfer_stock(
            db, current_user.company_id, payload.product_id,
            payload.from_warehouse_id, payload.to_warehouse_id, payload.quantity, payload.reason, sale_unit_id=payload.sale_unit_id, fiscal_period_id=payload.fiscal_period_id,
            lot_id=payload.lot_id,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/loss", response_model=StockLevelResponse)
async def post_stock_loss(
    payload: StockLossRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:loss")),
):
    """Records a stock write-off with no sale - expiry, breakage, theft, or other."""
    try:
        await record_stock_loss(
            db, current_user.company_id, payload.warehouse_id, payload.product_id,
            payload.quantity, payload.loss_category, payload.reason, sale_unit_id=payload.sale_unit_id, fiscal_period_id=payload.fiscal_period_id,
            lot_id=payload.lot_id,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    levels = await list_stock_levels(db, current_user.company_id, payload.warehouse_id)
    return next(l for l in levels if l["product_id"] == payload.product_id)


@router.post("/adjust", response_model=StockLevelResponse)
async def post_adjust_stock(
    payload: StockAdjustRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:adjust")),
):
    """Manually corrects stock to an exact quantity in a specific warehouse - GESTOR only, reason required."""
    try:
        await adjust_stock(db, current_user.company_id, payload.warehouse_id, payload.product_id, payload.new_quantity, payload.reason, sale_unit_id=payload.sale_unit_id, fiscal_period_id=payload.fiscal_period_id,
                           lot_id=payload.lot_id, lot_number=payload.lot_number, expiry_date=payload.expiry_date)
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:  # a missing lot / validity, a lot that does not hold that much
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    levels = await list_stock_levels(db, current_user.company_id, payload.warehouse_id)
    return next(l for l in levels if l["product_id"] == payload.product_id)


@router.patch("/warehouses/{warehouse_id}", response_model=WarehouseResponse)
async def patch_warehouse(
    warehouse_id: uuid.UUID,
    payload: WarehouseCreateFullRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("warehouses:manage")),
):
    """Full edit of a secondary warehouse - GESTOR only. The central warehouse cannot be edited."""
    try:
        return await update_warehouse(
            db, current_user.company_id, warehouse_id, payload.name, payload.code,
            payload.province_id, payload.municipality_id, payload.address,
            payload.allow_negative_stock, payload.entradas_bloqueadas,
            payload.saidas_bloqueadas,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CentralWarehouseNotEditableError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


@router.patch("/warehouses/{warehouse_id}/toggle-status", response_model=WarehouseResponse)
async def patch_warehouse_toggle_status(
    warehouse_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("warehouses:manage")),
):
    """Activates/deactivates a secondary warehouse - GESTOR only."""
    try:
        return await toggle_warehouse_status(db, current_user.company_id, warehouse_id)
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CentralWarehouseNotEditableError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))

@router.get("/production-estimate", response_model=ProductionEstimateResponse)
async def get_production_estimate(
    warehouse_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("production:view")),
):
    """Estimates how many units can be produced from the warehouse's current ingredient stock."""
    try:
        return await estimate_production_capacity(db, current_user.company_id, warehouse_id, product_id)
    except NoRecipeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except StockQuantityError as e:  # a unit the product does not have, or a decimal in a whole unit
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/dashboard")
async def get_dashboard(
    fiscal_period_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Aggregated stock overview across all warehouses - totals, low-stock alerts, value; the current stock, or the
    stock at the end of a fiscal period when one is given."""
    return await get_stock_dashboard(db, current_user.company_id, fiscal_period_id)


@router.get("/production-history")
async def get_production_history(
    year: int | None = None,
    month: int | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("production:view")),
):
    """Lists past production runs (finished good + ingredients consumed per batch).
    Optional filters: year/month ("Periodo") and/or date_from/date_to ("Intervalo", YYYY-MM-DD)."""
    return await list_production_history(db, current_user.company_id, year, month, date_from, date_to)


@router.post("/produce", response_model=StockLevelResponse)
async def post_produce_stock(
    payload: ProduceStockRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("production:produce")),
):
    """Transforms ingredients into a finished product - all-or-nothing, blocks if any ingredient is insufficient."""
    try:
        await produce_stock(
            db, current_user.company_id, payload.warehouse_id, payload.finished_product_id,
            payload.quantity_to_produce, payload.reason, fiscal_period_id=payload.fiscal_period_id, sale_unit_id=payload.sale_unit_id,
            lot_number=payload.lot_number, expiry_date=payload.expiry_date,
        )
    except NoRecipeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))

    except StockQuantityError as e:  # a unit the product does not have, or a decimal in a whole unit
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    levels = await list_stock_levels(db, current_user.company_id, payload.warehouse_id)
    return next(l for l in levels if l["product_id"] == payload.finished_product_id)


@router.get("/period-closing")
async def get_period_closing(
    fiscal_period_id: uuid.UUID,
    warehouse_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """Fecho de stock por período: per product and warehouse, the stock at the start, in, out, at the end and its
    value - frozen at the period's final close (company option), else computed from the ledger."""
    try:
        return await get_period_stock_report(db, current_user.company_id, fiscal_period_id, warehouse_id)
    except StockClosingPeriodNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Inventário (point 11): count a warehouse, validate the differences into adjustments ----------

INVENTORY_ERRORS = {InventoryNotFoundError: status.HTTP_404_NOT_FOUND, InventoryStateError: status.HTTP_409_CONFLICT,
                    PeriodClosedError: status.HTTP_409_CONFLICT, WarehouseNotFoundError: status.HTTP_404_NOT_FOUND}


def _inventory_http(e: Exception) -> HTTPException:
    return HTTPException(status_code=INVENTORY_ERRORS[type(e)], detail=str(e))


@router.get("/inventories")
async def get_inventories(
    warehouse_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    return await list_inventories(db, current_user.company_id, warehouse_id)


@router.post("/inventories", status_code=status.HTTP_201_CREATED)
async def post_inventory(
    payload: InventoryCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:adjust")),
):
    try:
        inventory = await create_inventory(db, current_user.company_id, payload.warehouse_id, current_user.id,
                                           payload.fiscal_period_id, payload.description)
        return await get_inventory(db, current_user.company_id, inventory.id)
    except tuple(INVENTORY_ERRORS) as e:
        raise _inventory_http(e)


@router.get("/inventories/{inventory_id}")
async def get_one_inventory(
    inventory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    try:
        return await get_inventory(db, current_user.company_id, inventory_id)
    except tuple(INVENTORY_ERRORS) as e:
        raise _inventory_http(e)


@router.put("/inventories/{inventory_id}/counts")
async def put_inventory_counts(
    inventory_id: uuid.UUID,
    payload: InventoryCountsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:adjust")),
):
    try:
        await save_counts(db, current_user.company_id, inventory_id, [c.model_dump() for c in payload.counts])
        return await get_inventory(db, current_user.company_id, inventory_id)
    except tuple(INVENTORY_ERRORS) as e:
        raise _inventory_http(e)


@router.post("/inventories/{inventory_id}/validate")
async def post_validate_inventory(
    inventory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:adjust")),
):
    try:
        return await validate_inventory(db, current_user.company_id, inventory_id, current_user.id)
    except tuple(INVENTORY_ERRORS) as e:
        raise _inventory_http(e)


@router.get("/inventories/{inventory_id}/pdf")
async def get_inventory_pdf(
    inventory_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("stock:view")),
):
    """The counting sheet of a draft, or the record of a validated inventory."""
    from fastapi import Response
    from sqlalchemy import select
    from app.models.company import Company
    from app.services.cash_report_service import _company_dict
    from app.utils.inventory_pdf import generate_inventory_pdf
    try:
        data = await get_inventory(db, current_user.company_id, inventory_id)
    except tuple(INVENTORY_ERRORS) as e:
        raise _inventory_http(e)
    company = (await db.execute(select(Company).where(Company.id == current_user.company_id))).scalar_one()
    pdf = generate_inventory_pdf(data, _company_dict(company))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{data["reference"].replace("/", "-")}.pdf"'})
