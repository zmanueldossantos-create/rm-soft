"""
Routes for the Moedeiro (billetage) feature: denomination catalog (read-only)
and cash-drawer denomination counts.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.cash_denomination_count import DenominationCountType
from app.schemas.moedeiro import (
    DenominationResponse,
    RecordDenominationCountRequest,
    DenominationCountResponse,
)
from app.services.denomination_service import list_denominations
from app.services.cash_denomination_count_service import (
    record_denomination_count,
    get_latest_count,
    get_count_total,
    get_count_lines,
    EmptyCountError,
    DenominationNotFoundError,
)

router = APIRouter(prefix="/api/v1/moedeiro", tags=["moedeiro"])



@router.get("/denominations", response_model=list[DenominationResponse])
async def get_denominations(
    currency_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("moedeiro:view")),
):
    return await list_denominations(db, currency_id)


@router.post("/counts", response_model=DenominationCountResponse, status_code=status.HTTP_201_CREATED)
async def post_denomination_count(
    payload: RecordDenominationCountRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("moedeiro:record")),
):
    try:
        count, total = await record_denomination_count(
            db, current_user.company_id, payload.cash_session_id,
            DenominationCountType(payload.count_type), current_user.id,
            [{"denomination_id": l.denomination_id, "quantity": l.quantity} for l in payload.lines],
        )
    except EmptyCountError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DenominationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    lines = await get_count_lines(db, count.id)
    return DenominationCountResponse(
        id=count.id, company_id=count.company_id, cash_session_id=count.cash_session_id,
        count_type=count.count_type.value, counted_by_user_id=count.counted_by_user_id,
        counted_at=count.counted_at, total=total,
        lines=[{"denomination_id": l.denomination_id, "quantity": l.quantity} for l in lines],
    )


@router.get("/counts/latest", response_model=DenominationCountResponse | None)
async def get_latest_denomination_count(
    cash_session_id: uuid.UUID,
    count_type: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("moedeiro:view")),
):
    """Fetches the most recent count of a given type for a session - used to
    pre-fill the closing screen if a FECHO count was already made from Moedeiro."""
    count = await get_latest_count(db, current_user.company_id, cash_session_id, DenominationCountType(count_type))
    if count is None:
        return None
    total = await get_count_total(db, count.id)
    lines = await get_count_lines(db, count.id)
    return DenominationCountResponse(
        id=count.id, company_id=count.company_id, cash_session_id=count.cash_session_id,
        count_type=count.count_type.value, counted_by_user_id=count.counted_by_user_id,
        counted_at=count.counted_at, total=total,
        lines=[{"denomination_id": l.denomination_id, "quantity": l.quantity} for l in lines],
    )
