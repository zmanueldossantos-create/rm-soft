import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.hotel import CheckInResponse, StayExtendRequest, WalkInRequest, WalkInResponse
from app.schemas.booking import BookingResponse
from app.services.hotel_service import (
    check_in, check_out, extend_stay, walk_in,
    NoDefaultPosError, AlreadyCheckedInError, AmbiguousOpenSessionError, InvalidStayStateError, StayHasUnpaidAccountError,
    InvalidWalkInError,
)
from app.services.booking_service import (
    BookingNotFoundError, BookingOverlapError, InvalidBookingRangeError, IncompatibleServiceError,
)
from app.services.fiscal_period_service import PeriodClosedError
from app.services.invoice_service import (
    CustomerNotFoundError, DocumentTypeNotConfiguredError, PaymentAmountMismatchError, SeriesNotConfiguredError,
)
from app.services.pos_service import NoOpenSessionError
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
        return await check_out(db, current_user.company_id, booking_id, current_user)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidStayStateError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except StayHasUnpaidAccountError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/walk-in", response_model=WalkInResponse, status_code=status.HTTP_201_CREATED)
async def post_walk_in(
    payload: WalkInRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("hotel:checkin")),
):
    """A prepaid passage: the sale at the till, then the room occupied from now for the service's duration."""
    try:
        booking, invoice = await walk_in(
            db, current_user.company_id, payload.resource_id, payload.service_id, current_user, payload.pos_id,
            [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments],
            payload.customer_id, payload.guest_name, payload.party_size,
        )
        return {"booking": booking, "invoice_id": invoice.id}
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (InvalidWalkInError, IncompatibleServiceError, PaymentAmountMismatchError, DocumentTypeNotConfiguredError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (BookingOverlapError, NoDefaultPosError, NoOpenSessionError, PeriodClosedError, SeriesNotConfiguredError) as e:
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
