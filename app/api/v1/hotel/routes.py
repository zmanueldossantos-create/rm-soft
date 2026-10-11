import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.hotel import CheckInResponse, OccupancyHistoryEntry, StayExtendRequest
from app.schemas.booking import BookingResponse
from app.services.hotel_service import (
    check_in, check_out, extend_stay, get_occupancy_history,
    NoDefaultPosError, AlreadyCheckedInError, AmbiguousOpenSessionError, InvalidStayStateError, StayHasUnpaidAccountError,
)
from app.services.booking_service import BookingNotFoundError, BookingOverlapError, InvalidBookingRangeError
from app.services.resource_service import ResourceNotFoundError

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
    except InvalidStayStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/bookings/{booking_id}/check-out", response_model=BookingResponse)
async def post_check_out(
    booking_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:checkout")),
):
    """Only a stay with nothing left to pay - a stay with articles is paid at the till, which concludes it."""
    try:
        return await check_out(db, current_user.company_id, booking_id)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStayStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except StayHasUnpaidAccountError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/bookings/{booking_id}/extend", response_model=BookingResponse)
async def post_extend_stay(
    booking_id: uuid.UUID,
    payload: StayExtendRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:update")),
):
    """New end of a stay in progress; the room-rate line of its account follows."""
    try:
        return await extend_stay(db, current_user.company_id, booking_id, payload.ends_at)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStayStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BookingOverlapError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidBookingRangeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/occupancy-history", response_model=list[OccupancyHistoryEntry])
async def get_occupancy_history_route(
    activity_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:occupancy_view")),
):
    return await get_occupancy_history(db, current_user.company_id, activity_id, date_from, date_to)
