import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.hotel import CheckInResponse, CheckOutRequest, OccupancyHistoryEntry
from app.schemas.booking import BookingResponse
from app.services.hotel_service import check_in, check_out, get_occupancy_history, NoDefaultPosError, AlreadyCheckedInError, AmbiguousOpenSessionError
from app.services.booking_service import BookingNotFoundError
from app.services.resource_service import ResourceNotFoundError
from app.services.open_account_service import EmptyAccountError, AccountAlreadyClosedError
from app.services.invoice_service import StockUnavailableError, SeriesNotConfiguredError, PaymentAmountMismatchError
from app.services.pos_service import NoOpenSessionError

router = APIRouter(prefix="/api/v1/hotel", tags=["hotel"])



@router.post("/bookings/{booking_id}/check-in", response_model=CheckInResponse)
async def post_check_in(
    booking_id: uuid.UUID,
    pos_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:checkin")),
):
    """pos_id is optional - lets the caller pick explicitly which of the activity's
    POS to bill the stay through when more than one has an open session (see
    AmbiguousOpenSessionError) - the frontend re-calls this with pos_id set once
    the cashier picks one from the disambiguation prompt."""
    try:
        booking, account = await check_in(db, current_user.company_id, booking_id, current_user, pos_id)
        return {"booking": booking, "account": account}
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NoDefaultPosError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AlreadyCheckedInError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except AmbiguousOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/bookings/{booking_id}/check-out", response_model=BookingResponse)
async def post_check_out(
    booking_id: uuid.UUID,
    payload: CheckOutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:checkout")),
):
    try:
        payments = [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments]
        return await check_out(db, current_user.company_id, booking_id, current_user, payments)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EmptyAccountError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except StockUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PaymentAmountMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except NoOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/occupancy-history", response_model=list[OccupancyHistoryEntry])
async def get_occupancy_history_route(
    activity_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:occupancy_view")),
):
    return await get_occupancy_history(db, current_user.company_id, activity_id, date_from, date_to)
