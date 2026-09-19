"""
Service layer for Booking - the generic reservation engine. See
app.models.booking for the full design rationale, especially the overlap
rule enforced here (never at the DB level).
"""
import uuid
from datetime import datetime

from sqlalchemy import select, and_, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.services.resource_service import get_resource_or_raise
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service


class BookingNotFoundError(Exception):
    pass


class BookingOverlapError(Exception):
    pass


class InvalidBookingRangeError(Exception):
    pass


_ACTIVE_STATUSES = (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA, BookingStatus.EM_CURSO)


def _clean_guest_name(value: str | None) -> str | None:
    """Free-text guest name: trimmed, and blank means 'none'."""
    cleaned = (value or "").strip()
    return cleaned[:150] or None


async def _has_overlap(
    db: AsyncSession, resource_id: uuid.UUID, starts_at: datetime, ends_at: datetime,
    exclude_booking_id: uuid.UUID | None = None,
) -> bool:
    """
    Two ranges [a_start, a_end) and [b_start, b_end) overlap iff a_start < b_end
    AND b_start < a_end - the classic half-open interval overlap test, applied
    only against bookings still in an active status (a CANCELADA/NO_SHOW booking
    no longer holds its slot).
    """
    query = select(Booking).where(
        Booking.resource_id == resource_id,
        Booking.status.in_(_ACTIVE_STATUSES),
        Booking.starts_at < ends_at,
        Booking.ends_at > starts_at,
    )
    if exclude_booking_id is not None:
        query = query.where(Booking.id != exclude_booking_id)
    result = await db.execute(query)
    return result.scalar_one_or_none() is not None


class ServiceRequiredError(Exception):
    pass


class IncompatibleServiceError(Exception):
    pass


async def _validate_service_for_resource(db: AsyncSession, company_id: uuid.UUID, resource, service_id: uuid.UUID | None) -> None:
    """Enforces ResourceTypeCatalog.requires_service (e.g. a CHAMBRE always has a
    rate to charge, even for a short stay) and, when a service IS given, that it's
    actually meant for this resource's type - a service tied to a DIFFERENT
    resource_type_id (e.g. a Spa treatment picked for a hotel room booking) is
    rejected; a service with resource_type_id=None is generic and always allowed.
    """
    type_result = await db.execute(select(ResourceTypeCatalog).where(ResourceTypeCatalog.id == resource.resource_type_id))
    resource_type = type_result.scalar_one_or_none()

    if resource_type is not None and resource_type.requires_service and service_id is None:
        raise ServiceRequiredError(f"Este tipo de recurso ({resource_type.name}) exige um servico associado a reserva")

    if service_id is not None:
        service_result = await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))
        service = service_result.scalar_one_or_none()
        if service is not None and service.resource_type_id is not None and service.resource_type_id != resource.resource_type_id:
            raise IncompatibleServiceError("O servico selecionado nao e valido para este tipo de recurso")


async def create_booking(
    db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID, created_by_user_id: uuid.UUID,
    starts_at: datetime, ends_at: datetime, customer_id: uuid.UUID | None = None,
    service_id: uuid.UUID | None = None, notes: str | None = None,
    guest_name: str | None = None, party_size: int | None = None,
) -> Booking:
    if ends_at <= starts_at:
        raise InvalidBookingRangeError("A data/hora de fim deve ser posterior ao inicio")

    resource = await get_resource_or_raise(db, company_id, resource_id)
    await _validate_service_for_resource(db, company_id, resource, service_id)

    if await _has_overlap(db, resource_id, starts_at, ends_at):
        raise BookingOverlapError("Este recurso ja tem uma reserva neste periodo")

    booking = Booking(
        company_id=company_id, resource_id=resource_id, customer_id=customer_id, service_id=service_id,
        starts_at=starts_at, ends_at=ends_at, notes=notes, created_by_user_id=created_by_user_id,
        guest_name=_clean_guest_name(guest_name), party_size=party_size,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def get_booking_or_raise(db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    result = await db.execute(select(Booking).where(Booking.id == booking_id, Booking.company_id == company_id))
    booking = result.scalar_one_or_none()
    if booking is None:
        raise BookingNotFoundError("Reserva nao encontrada")
    return booking


async def list_bookings(
    db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> list[Booking]:
    query = select(Booking).where(Booking.company_id == company_id)
    if resource_id is not None:
        query = query.where(Booking.resource_id == resource_id)
    if date_from is not None:
        query = query.where(Booking.ends_at >= date_from)
    if date_to is not None:
        query = query.where(Booking.starts_at <= date_to)
    result = await db.execute(query.order_by(Booking.starts_at))
    return list(result.scalars().all())


async def update_booking_status(
    db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, new_status: BookingStatus,
) -> Booking:
    booking = await get_booking_or_raise(db, company_id, booking_id)
    booking.status = new_status
    await db.commit()
    await db.refresh(booking)
    return booking


class BookingNotEditableError(Exception):
    pass


async def reschedule_booking(
    db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, starts_at: datetime, ends_at: datetime,
    service_id: uuid.UUID | None = None, notes: str | None = None, customer_id: uuid.UUID | None = None,
    guest_name: str | None = None, party_size: int | None = None,
) -> Booking:
    """Full booking edit - dates (with the usual overlap check), service and notes,
    all in one call. The caller (the edit form) always sends the current value of
    every field, so service_id=None/notes=None here genuinely means "no service" /
    "no notes", not "leave unchanged" - there is no partial-update sentinel.

    Editing is blocked once a booking is EM_CURSO or CONCLUIDA - by then a real
    OpenAccount/invoice may already exist against the original dates/service (see
    hotel_service.check_in), so silently changing them here would desync the
    stay's billing from the reservation. Cancel and recreate instead in that case.
    """
    if ends_at <= starts_at:
        raise InvalidBookingRangeError("A data/hora de fim deve ser posterior ao inicio")

    booking = await get_booking_or_raise(db, company_id, booking_id)
    if booking.status in (BookingStatus.EM_CURSO, BookingStatus.CONCLUIDA):
        raise BookingNotEditableError("Esta reserva ja tem check-in e nao pode ser editada")

    resource = await get_resource_or_raise(db, company_id, booking.resource_id)
    await _validate_service_for_resource(db, company_id, resource, service_id)

    if await _has_overlap(db, booking.resource_id, starts_at, ends_at, exclude_booking_id=booking_id):
        raise BookingOverlapError("Este recurso ja tem uma reserva neste periodo")

    booking.starts_at = starts_at
    booking.ends_at = ends_at
    booking.service_id = service_id
    booking.notes = notes
    booking.customer_id = customer_id
    booking.guest_name = _clean_guest_name(guest_name)
    booking.party_size = party_size
    await db.commit()
    await db.refresh(booking)
    return booking
