import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.booking import BookingStatus
from app.schemas.booking import (
    ResourceCreateRequest, ResourceUpdateRequest, ResourceResponse, RatePricesRequest,
    ResourceTypeCreateRequest, ResourceTypeUpdateRequest, ResourceTypeResponse,
    BookingCreateRequest, BookingRescheduleRequest, BookingStatusUpdateRequest, BookingResponse,
    BookingChargeRequest, BookingChargeResponse, ResourceStatusResponse, ResourceHistoryResponse, StayQuoteResponse,
)
from app.services.resource_history_service import get_resource_history
from app.services.booking_charge_service import charge_booking, BookingNotChargeableError
from app.services.hotel_service import NoDefaultPosError, stay_quote
from app.services.service_service import ServiceNotFoundError
from app.services.fiscal_period_service import PeriodClosedError
from app.services.invoice_service import (
    CustomerNotFoundError, DocumentTypeNotConfiguredError, PaymentAmountMismatchError, SeriesNotConfiguredError,
)
from app.services.pos_service import NoOpenSessionError
from app.services.resource_service import (
    create_resource, get_resource_or_raise, list_resources, update_resource, toggle_resource_status,
    InvalidRatePriceError, attach_rate_prices, set_rate_prices,
    ResourceNotFoundError,
)
from app.services.resource_type_service import (
    create_resource_type, list_resource_types, update_resource_type, toggle_resource_type_status,
    ResourceTypeNotFoundError, ResourceTypeAlreadyExistsError,
)
from app.services.booking_service import (
    create_booking, get_booking_or_raise, list_bookings, update_booking_status, reschedule_booking,
    BookingNotFoundError, BookingOverlapError, InvalidBookingRangeError, BookingNotEditableError,
    ServiceRequiredError, IncompatibleServiceError,
)
from app.services.activity_service import ActivityNotFoundError
from app.services.resource_status_service import list_resource_statuses

router = APIRouter(prefix="/api/v1", tags=["bookings"])



# ---------- Resource types (managed catalog) ----------

@router.post("/resource-types", response_model=ResourceTypeResponse, status_code=status.HTTP_201_CREATED)
async def post_create_resource_type(
    payload: ResourceTypeCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resource_types:manage")),
):
    try:
        return await create_resource_type(
            db, current_user.company_id, payload.name, payload.requires_service,
            payload.default_start_time, payload.default_end_time,
        )
    except ResourceTypeAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/resource-types", response_model=list[ResourceTypeResponse])
async def get_resource_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resource_types:view")),
):
    return await list_resource_types(db, current_user.company_id)


@router.patch("/resource-types/{resource_type_id}", response_model=ResourceTypeResponse)
async def patch_resource_type(
    resource_type_id: uuid.UUID,
    payload: ResourceTypeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resource_types:manage")),
):
    try:
        return await update_resource_type(
            db, current_user.company_id, resource_type_id, payload.name, payload.requires_service,
            payload.default_start_time, payload.default_end_time,
        )
    except ResourceTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceTypeAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/resource-types/{resource_type_id}/toggle", response_model=ResourceTypeResponse)
async def post_toggle_resource_type(
    resource_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resource_types:manage")),
):
    try:
        return await toggle_resource_type_status(db, current_user.company_id, resource_type_id)
    except ResourceTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Resources ----------

@router.post("/resources", response_model=ResourceResponse, status_code=status.HTTP_201_CREATED)
async def post_create_resource(
    payload: ResourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:manage")),
):
    try:
        return await create_resource(db, current_user.company_id, payload.activity_id, payload.resource_type_id, payload.name, payload.capacity)
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ResourceTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/resources", response_model=list[ResourceResponse])
async def get_resources(
    activity_id: uuid.UUID | None = None,
    resource_type_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:view")),
):
    return await attach_rate_prices(db, await list_resources(db, current_user.company_id, activity_id, resource_type_id))


@router.put("/resources/{resource_id}/rate-prices", response_model=ResourceResponse)
async def put_resource_rate_prices(
    resource_id: uuid.UUID,
    payload: RatePricesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:manage")),
):
    """The resource's own prices for the rates of its type (the others: the rate's price)."""
    try:
        return await set_rate_prices(db, current_user.company_id, resource_id, [p.model_dump() for p in payload.prices])
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidRatePriceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/resources/{resource_id}", response_model=ResourceResponse)
async def patch_resource(
    resource_id: uuid.UUID,
    payload: ResourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:manage")),
):
    try:
        return await update_resource(db, current_user.company_id, resource_id, payload.name, payload.capacity)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/resources/{resource_id}/toggle", response_model=ResourceResponse)
async def post_toggle_resource(
    resource_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:manage")),
):
    try:
        return await toggle_resource_status(db, current_user.company_id, resource_id)
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Bookings ----------

@router.post("/bookings", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
async def post_create_booking(
    payload: BookingCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:create")),
):
    try:
        return await create_booking(
            db, current_user.company_id, payload.resource_id, current_user.id,
            payload.starts_at, payload.ends_at, payload.customer_id, payload.service_id, payload.notes,
            payload.guest_name, payload.party_size,
        )
    except ResourceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BookingOverlapError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidBookingRangeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except IncompatibleServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/bookings/quote", response_model=StayQuoteResponse)
async def get_stay_quote(
    resource_id: uuid.UUID,
    service_id: uuid.UUID,
    starts_at: datetime,
    ends_at: datetime,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:view")),
):
    """The price of a booking before it is made: the form shows it as the dates, the room or the rate change."""
    try:
        return await stay_quote(db, current_user.company_id, resource_id, service_id, starts_at, ends_at)
    except (ResourceNotFoundError, ServiceNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/bookings", response_model=list[BookingResponse])
async def get_bookings(
    resource_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:view")),
):
    return await list_bookings(db, current_user.company_id, resource_id, date_from, date_to)


@router.patch("/bookings/{booking_id}/status", response_model=BookingResponse)
async def patch_booking_status(
    booking_id: uuid.UUID,
    payload: BookingStatusUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:update")),
):
    try:
        new_status = BookingStatus(payload.status)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado inválido")
    try:
        return await update_booking_status(db, current_user.company_id, booking_id, new_status)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BookingNotEditableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/bookings/{booking_id}/charge", response_model=BookingChargeResponse)
async def post_charge_booking(
    booking_id: uuid.UUID,
    payload: BookingChargeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:charge")),
):
    """Cobrar uma marcação: the sale of its service at this till, then the booking concluded with its invoice."""
    try:
        booking, invoice = await charge_booking(
            db, current_user.company_id, booking_id, current_user, payload.pos_id,
            [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments],
            payload.customer_id, terminal_id=payload.terminal_id,
        )
        return {"booking": booking, "invoice_id": invoice.id}
    except (BookingNotFoundError, ResourceNotFoundError, CustomerNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (PaymentAmountMismatchError, DocumentTypeNotConfiguredError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except (BookingNotChargeableError, NoDefaultPosError, NoOpenSessionError, PeriodClosedError, SeriesNotConfiguredError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/bookings/{booking_id}/reschedule", response_model=BookingResponse)
async def patch_booking_reschedule(
    booking_id: uuid.UUID,
    payload: BookingRescheduleRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("bookings:update")),
):
    try:
        return await reschedule_booking(
            db, current_user.company_id, booking_id, payload.starts_at, payload.ends_at,
            payload.service_id, payload.notes, payload.customer_id,
            payload.guest_name, payload.party_size,
        )
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BookingOverlapError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidBookingRangeError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except BookingNotEditableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except IncompatibleServiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/resources/history", response_model=ResourceHistoryResponse)
async def get_resources_history(
    activity_id: uuid.UUID | None = None,
    resource_id: uuid.UUID | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:history")),
):
    """Every use of the resources over a period (stays, passages, marcações, reservations, tables' accounts) and a
    summary per resource: uses, occupied time, revenue (documents minus credit notes), cancellations, no-shows."""
    return await get_resource_history(db, current_user.company_id, activity_id, resource_id, date_from, date_to)


@router.get("/resources/status", response_model=list[ResourceStatusResponse])
async def get_resources_status(
    activity_id: uuid.UUID,
    window_minutes: int = Query(60, ge=0, le=1440),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("resources:view")),
):
    """Derived status of an activity's active resources (LIVRE / OCUPADA / RESERVADA) - the
    floor plan of a restaurant. window_minutes: how far ahead a booking counts as RESERVADA."""
    return await list_resource_statuses(db, current_user.company_id, activity_id, window_minutes=window_minutes)
