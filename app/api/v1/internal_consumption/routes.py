import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.models.user import User
from app.schemas.internal_consumption import (
    ConsumptionReasonCreateRequest, ConsumptionReasonUpdateRequest, ConsumptionReasonResponse,
    InternalConsumptionCreateRequest, InternalConsumptionEntry,
)
from app.services.consumption_reason_service import (
    create_consumption_reason, list_consumption_reasons, update_consumption_reason, toggle_consumption_reason_status,
    ConsumptionReasonNotFoundError, ConsumptionReasonAlreadyExistsError,
)
from app.services.internal_consumption_service import (
    record_consumption, list_consumptions, NoWarehouseError, ProductNotFoundError,
)
from app.services.activity_service import ActivityNotFoundError
from app.services.stock_service import InsufficientStockError

router = APIRouter(prefix="/api/v1", tags=["internal-consumption"])

ALLOWED_ROLES = ("GESTOR", "ARMAZENISTA")


# ---------- Consumption reasons (managed catalog) ----------

@router.post("/consumption-reasons", response_model=ConsumptionReasonResponse, status_code=status.HTTP_201_CREATED)
async def post_create_consumption_reason(
    payload: ConsumptionReasonCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await create_consumption_reason(db, current_user.company_id, payload.name)
    except ConsumptionReasonAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/consumption-reasons", response_model=list[ConsumptionReasonResponse])
async def get_consumption_reasons(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    return await list_consumption_reasons(db, current_user.company_id)


@router.patch("/consumption-reasons/{reason_id}", response_model=ConsumptionReasonResponse)
async def patch_consumption_reason(
    reason_id: uuid.UUID,
    payload: ConsumptionReasonUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await update_consumption_reason(db, current_user.company_id, reason_id, payload.name)
    except ConsumptionReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ConsumptionReasonAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/consumption-reasons/{reason_id}/toggle", response_model=ConsumptionReasonResponse)
async def post_toggle_consumption_reason(
    reason_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await toggle_consumption_reason_status(db, current_user.company_id, reason_id)
    except ConsumptionReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Internal consumption records ----------

@router.post("/internal-consumption", status_code=status.HTTP_201_CREATED)
async def post_record_consumption(
    payload: InternalConsumptionCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    try:
        record = await record_consumption(
            db, current_user.company_id, payload.activity_id, payload.product_id, payload.quantity,
            payload.reason_id, current_user.id, payload.resource_id, payload.notes,
        )
        return {"id": record.id}
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NoWarehouseError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/internal-consumption", response_model=list[InternalConsumptionEntry])
async def get_internal_consumption(
    activity_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    return await list_consumptions(db, current_user.company_id, activity_id, date_from, date_to)
