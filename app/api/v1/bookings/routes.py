import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.booking import BookingStatus
from app.schemas.booking import (
    ResourceCreateRequest, ResourceUpdateRequest, ResourceResponse,
    ResourceTypeCreateRequest, ResourceTypeUpdateRequest, ResourceTypeResponse,
    BookingCreateRequest, BookingRescheduleRequest, BookingStatusUpdateRequest, BookingResponse,
    ResourceStatusResponse,
)
from app.services.resource_service import (
    create_resource, get_resource_or_raise, list_resources, update_resource, toggle_resource_status,
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
        return await create_resource_type(db, current_user.company_id, payload.name, payload.requires_service)
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
        return await update_resource_type(db, current_user.company_id, resource_type_id, payload.name, payload.requires_service)
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
    return await list_resources(db, current_user.company_id, activity_id, resource_type_id)


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
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Estado invalido")
    try:
        return await update_booking_status(db, current_user.company_id, booking_id, new_status)
    except BookingNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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
