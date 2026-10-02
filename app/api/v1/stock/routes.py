"""
Stock routes - scoped to the caller's company (multi-tenant isolation).
See specification v6/v7, section 5.1.
Multi-warehouse (see stock_service module docstring): goods are received
into the CENTRAL warehouse, then internally transferred between any of
the company's warehouses (central <-> activity, or activity <-> activity)
before being sold or written off (PERDA) at a specific point of sale.
"""
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
    return await list_stock_movements(db, current_user.company_id, warehouse_id, year, month, date_from, date_to, limit, offset)


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
        await adjust_stock(db, current_user.company_id, payload.warehouse_id, payload.product_id, payload.new_quantity, payload.reason, sale_unit_id=payload.sale_unit_id, fiscal_period_id=payload.fiscal_period_id)
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

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
            payload.quantity_to_produce, payload.reason, fiscal_period_id=payload.fiscal_period_id,
        )
    except NoRecipeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except WarehouseNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))

    levels = await list_stock_levels(db, current_user.company_id, payload.warehouse_id)
    return next(l for l in levels if l["product_id"] == payload.finished_product_id)
