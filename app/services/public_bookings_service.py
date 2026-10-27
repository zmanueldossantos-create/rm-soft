"""
The public API's bookings (app.api.public_v1, scope «bookings»): the hotel's web site asks what is free, books, follows
and cancels its bookings.

- Availability per resource type (Quarto duplo, Suite, Mesa...): how many resources are free over the period, and the
  rates (the services of that type) with the price of the stay.
- A booking asks for a type (RM SOFT gives it a free resource - the reception may move it) or a precise resource; it
  arrives PENDENTE: the reception confirms it. The gestor is told (event RESERVA_ONLINE).
- Dates: a hotel sends days (check_in / check_out) - the hours are those of the resource type (14:00 -> 12:00);
  a table or a treatment sends exact times (starts_at / ends_at).
- The program sees only the bookings made through the API, and cancels only those, before the check-in.
"""
import uuid
from datetime import date, datetime, time, timedelta, timezone

from fastapi.encoders import jsonable_encoder
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.customer import Customer
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services.public_api_service import PublicApiError, _money, _page, _sellable_services, _with_vat

LUANDA_TZ = timezone(timedelta(hours=1))  # Africa/Luanda, no summer time
CANCELLABLE = (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA)
MAX_DAYS = 366


class NoResourceFreeError(Exception):
    """Nothing free any more for this period (409)."""


# ------------------------------------------------------------------------------------------------------------ period

def period(resource_type: ResourceTypeCatalog | None, check_in: date | None, check_out: date | None,
           starts_at: datetime | None, ends_at: datetime | None) -> tuple[datetime, datetime, int | None]:
    """(start, end, nights): days with the type's usual hours, or exact times. nights: None with exact times."""
    if starts_at is not None or ends_at is not None:
        if starts_at is None or ends_at is None or check_in is not None or check_out is not None:
            raise PublicApiError("Indique check_in e check_out (dias) ou starts_at e ends_at (horas), não os dois")
        start, end = (_aware(starts_at), _aware(ends_at))
        nights = None
    else:
        if check_in is None or check_out is None:
            raise PublicApiError("Indique as datas: check_in e check_out (ou starts_at e ends_at)")
        if check_out <= check_in:
            raise PublicApiError("O check_out deve ser depois do check_in")
        start_hour = resource_type.default_start_time if resource_type and resource_type.default_start_time else time(0)
        end_hour = resource_type.default_end_time if resource_type and resource_type.default_end_time else time(0)
        start = datetime.combine(check_in, start_hour, LUANDA_TZ)
        end = datetime.combine(check_out, end_hour, LUANDA_TZ)
        nights = (check_out - check_in).days
    if end <= start:
        raise PublicApiError("O fim deve ser depois do início")
    if end - start > timedelta(days=MAX_DAYS):
        raise PublicApiError("Período demasiado longo (máximo 1 ano)")
    if end < datetime.now(timezone.utc):
        raise PublicApiError("O período já passou")
    return start, end, nights


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=LUANDA_TZ)  # a naive time: Luanda time


# ------------------------------------------------------------------------------------------------------- availability

async def _types(db: AsyncSession, company_id: uuid.UUID, resource_type_id: uuid.UUID | None = None):
    query = select(ResourceTypeCatalog).where(ResourceTypeCatalog.company_id == company_id,
                                              ResourceTypeCatalog.is_active.is_(True))
    if resource_type_id is not None:
        query = query.where(ResourceTypeCatalog.id == resource_type_id)
    return (await db.execute(query.order_by(ResourceTypeCatalog.name))).scalars().all()


async def _resources(db: AsyncSession, company_id: uuid.UUID, type_id: uuid.UUID) -> list[Resource]:
    return list((await db.execute(select(Resource).where(
        Resource.company_id == company_id, Resource.resource_type_id == type_id, Resource.is_active.is_(True))
        .order_by(Resource.name))).scalars().all())


async def _free(db: AsyncSession, resources: list[Resource], start: datetime, end: datetime) -> list[Resource]:
    from app.services.booking_service import _has_overlap
    return [r for r in resources if not await _has_overlap(db, r.id, start, end)]


async def _rates(db: AsyncSession, company_id: uuid.UUID, type_id: uuid.UUID) -> tuple[list[Service], dict]:
    """The services of this type (a room's rates) on sale, and their VAT rate - the generic ones are not a room's
    rate."""
    rows = (await db.execute(_sellable_services(company_id).where(Service.resource_type_id == type_id)
                             .order_by(Service.price, Service.name))).all()
    return [r[0] for r in rows], {r[0].id: float(r[1] or 0) for r in rows}


async def availability(db: AsyncSession, company_id: uuid.UUID, check_in: date | None = None,
                       check_out: date | None = None, starts_at: datetime | None = None,
                       ends_at: datetime | None = None, resource_type_id: uuid.UUID | None = None,
                       party_size: int | None = None) -> list[dict]:
    out = []
    for resource_type in await _types(db, company_id, resource_type_id):
        resources = await _resources(db, company_id, resource_type.id)
        if not resources:
            continue
        start, end, nights = period(resource_type, check_in, check_out, starts_at, ends_at)
        if party_size:
            resources = [r for r in resources if r.capacity is None or r.capacity >= party_size]
        free = await _free(db, resources, start, end)
        rates, vat = await _rates(db, company_id, resource_type.id)
        out.append({
            "resource_type_id": str(resource_type.id), "resource_type": resource_type.name,
            "starts_at": start, "ends_at": end, "nights": nights,
            "available": len(free), "total": len(resources),
            "resources": [{"id": str(r.id), "name": r.name, "capacity": r.capacity} for r in free],
            "rates": [{"service_id": str(s.id), "name": s.name, "price": _money(s.price), "vat_rate": vat[s.id],
                       "price_with_vat": _with_vat(s.price, vat[s.id]),
                       "stay_total_with_vat": _with_vat(float(s.price) * (nights or 1), vat[s.id])} for s in rates],
        })
    if resource_type_id is not None and not out:
        raise LookupError("Tipo de recurso não encontrado ou sem recursos")
    return jsonable_encoder(out)


# ----------------------------------------------------------------------------------------------------------- booking

async def _creator(db: AsyncSession, company_id: uuid.UUID, key) -> uuid.UUID:
    """The booking is recorded in the name of the key's gestor (or the company's first gestor)."""
    if key.created_by_user_id is not None:
        return key.created_by_user_id
    from app.models.user import User, UserRole
    user_id = (await db.execute(select(User.id).where(User.company_id == company_id, User.role == UserRole.GESTOR)
                                .order_by(User.created_at).limit(1))).scalar_one_or_none()
    if user_id is None:
        raise PublicApiError("A empresa não tem gestor")
    return user_id


def _notes(data: dict) -> str | None:
    parts = []
    if data.get("guest_phone"):
        parts.append("Tel.: " + data["guest_phone"])
    if data.get("guest_email"):
        parts.append("Email: " + data["guest_email"])
    if data.get("notes"):
        parts.append(data["notes"].strip())
    return (" · ".join(parts))[:500] or None


async def create_booking(db: AsyncSession, company_id: uuid.UUID, key, data: dict) -> Booking:
    """data: the validated request. Only flushed: the caller commits it with its idempotency record."""
    from app.services.booking_service import create_booking as create

    resource = None
    if data.get("resource_id") is not None:
        resource = (await db.execute(select(Resource).where(
            Resource.id == data["resource_id"], Resource.company_id == company_id, Resource.is_active.is_(True))
            .with_for_update())).scalar_one_or_none()
        if resource is None:
            raise LookupError("Recurso não encontrado")
        type_id = resource.resource_type_id
    elif data.get("resource_type_id") is not None:
        type_id = data["resource_type_id"]
    else:
        raise PublicApiError("Indique resource_type_id (o sistema escolhe um recurso livre) ou resource_id")
    types = await _types(db, company_id, type_id)
    if not types:
        raise LookupError("Tipo de recurso não encontrado")
    resource_type = types[0]
    start, end, _ = period(resource_type, data.get("check_in"), data.get("check_out"), data.get("starts_at"),
                           data.get("ends_at"))

    if data.get("service_id") is not None:
        rates, _ = await _rates(db, company_id, resource_type.id)
        generic = (await db.execute(_sellable_services(company_id).where(
            Service.id == data["service_id"], Service.resource_type_id.is_(None)))).first()
        if data["service_id"] not in {s.id for s in rates} and generic is None:
            raise PublicApiError("Serviço (tarifa) não encontrado ou não é deste tipo de recurso")
    if data.get("customer_id") is not None:
        found = (await db.execute(select(Customer.id).where(Customer.id == data["customer_id"],
                                                            Customer.company_id == company_id))).first()
        if found is None:
            raise LookupError("Cliente não encontrado")

    if resource is None:
        # a free resource of this type, locked while the booking is written: two sites booking the last room at the
        # same moment cannot both get it
        candidates = (await db.execute(select(Resource).where(
            Resource.company_id == company_id, Resource.resource_type_id == resource_type.id,
            Resource.is_active.is_(True),
            or_(Resource.capacity.is_(None), Resource.capacity >= (data.get("party_size") or 0)))
            .order_by(Resource.name).with_for_update())).scalars().all()
        free = await _free(db, list(candidates), start, end)
        if not free:
            raise NoResourceFreeError(f"Já não há {resource_type.name} livre neste período")
        resource = free[0]
    return await create(
        db, company_id, resource.id, await _creator(db, company_id, key), start, end,
        customer_id=data.get("customer_id"), service_id=data.get("service_id"), notes=_notes(data),
        guest_name=data.get("guest_name"), party_size=data.get("party_size"), api_key_id=key.id,
        external_reference=data.get("external_reference"), commit=False)


# ----------------------------------------------------------------------------------------------------------- reading

async def booking_view(db: AsyncSession, booking: Booking) -> dict:
    resource = await db.get(Resource, booking.resource_id)
    resource_type = await db.get(ResourceTypeCatalog, resource.resource_type_id) if resource else None
    service = await db.get(Service, booking.service_id) if booking.service_id else None
    customer = await db.get(Customer, booking.customer_id) if booking.customer_id else None
    return jsonable_encoder({
        "id": str(booking.id), "status": booking.status.value, "external_reference": booking.external_reference,
        "resource": {"id": str(resource.id), "name": resource.name} if resource else None,
        "resource_type": {"id": str(resource_type.id), "name": resource_type.name} if resource_type else None,
        "service": {"id": str(service.id), "name": service.name, "price": _money(service.price)} if service else None,
        "starts_at": booking.starts_at, "ends_at": booking.ends_at,
        "guest_name": booking.guest_name, "party_size": booking.party_size,
        "customer": {"id": str(customer.id), "name": customer.name, "nif": customer.nif} if customer else None,
        "can_cancel": booking.status in CANCELLABLE,
        "created_at": booking.created_at, "updated_at": booking.updated_at,
    })


def _api_bookings(company_id: uuid.UUID):
    """Only the bookings made through the API - a booking made at the desk (its guest...) is not the site's."""
    return select(Booking).where(Booking.company_id == company_id, Booking.api_key_id.is_not(None))


async def get_booking(db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    booking = (await db.execute(_api_bookings(company_id).where(Booking.id == booking_id))).scalar_one_or_none()
    if booking is None:
        raise LookupError("Reserva não encontrada")
    return booking


async def list_bookings(db: AsyncSession, company_id: uuid.UUID, external_reference: str | None = None,
                        status: str | None = None, date_from: date | None = None, date_to: date | None = None,
                        updated_since: datetime | None = None, page: int = 1, page_size: int = 50) -> dict:
    page, page_size = _page(page, page_size)
    query = _api_bookings(company_id)
    if external_reference:
        query = query.where(Booking.external_reference == external_reference.strip())
    if status:
        try:
            query = query.where(Booking.status == BookingStatus(status.strip().upper()))
        except ValueError:
            raise PublicApiError(f"Estado «{status}» desconhecido ({', '.join(s.value for s in BookingStatus)})")
    if date_from:
        query = query.where(Booking.ends_at >= datetime.combine(date_from, time(0), LUANDA_TZ))
    if date_to:
        query = query.where(Booking.starts_at < datetime.combine(date_to + timedelta(days=1), time(0), LUANDA_TZ))
    if updated_since:
        query = query.where(Booking.updated_at >= updated_since)
    total = (await db.execute(select(func.count()).select_from(query.subquery()))).scalar_one()
    rows = (await db.execute(query.order_by(Booking.starts_at, Booking.id)
                             .offset((page - 1) * page_size).limit(page_size))).scalars().all()
    return {"items": [await booking_view(db, b) for b in rows], "page": page, "page_size": page_size, "total": total}


async def cancel_booking(db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    """Before the check-in only; cancelling a cancelled booking again changes nothing."""
    booking = await get_booking(db, company_id, booking_id)
    if booking.status == BookingStatus.CANCELADA:
        return booking
    if booking.status not in CANCELLABLE:
        raise PublicApiError(f"Uma reserva {booking.status.value} já não pode ser cancelada pelo site - contacte a receção")
    booking.status = BookingStatus.CANCELADA
    await db.commit()
    await db.refresh(booking)
    return booking
