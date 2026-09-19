"""
Derived status of bookable resources (restaurant tables, rooms...) for a floor-plan
screen. Nothing is stored: the status is computed on demand from what already exists.

  OCUPADA   - at least one open account (OpenAccount ABERTA) is on the resource
  RESERVADA - no open account, but an active booking (PENDENTE / CONFIRMADA / EM_CURSO)
              overlaps [now, now + window): running now or starting soon
  LIVRE     - otherwise

OCUPADA wins over RESERVADA. A hotel room with a checked-in stay has an open account
linked to its booking, so it shows as OCUPADA too. The soonest overlapping booking is
always reported (even when the resource is OCUPADA) so the screen can warn about it.
"""
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.resource import Resource

STATUS_LIVRE = "LIVRE"
STATUS_OCUPADA = "OCUPADA"
STATUS_RESERVADA = "RESERVADA"

_ACTIVE_BOOKING_STATUSES = (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA, BookingStatus.EM_CURSO)


async def list_resource_statuses(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID,
    now: datetime | None = None, window_minutes: int = 60,
) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(minutes=window_minutes)

    resources_result = await db.execute(
        select(Resource)
        .where(Resource.company_id == company_id, Resource.activity_id == activity_id, Resource.is_active.is_(True))
        .order_by(Resource.name)
    )
    resources = list(resources_result.scalars().all())
    if not resources:
        return []
    resource_ids = [r.id for r in resources]

    tabs_result = await db.execute(
        select(
            OpenAccount.resource_id,
            func.count(func.distinct(OpenAccount.id)),
            func.coalesce(func.sum(OpenAccountLine.quantity * OpenAccountLine.unit_price), 0),
            func.min(OpenAccount.opened_at),
        )
        .select_from(OpenAccount)
        .outerjoin(OpenAccountLine, OpenAccountLine.account_id == OpenAccount.id)
        .where(
            OpenAccount.company_id == company_id,
            OpenAccount.status == OpenAccountStatus.ABERTA,
            OpenAccount.resource_id.in_(resource_ids),
        )
        .group_by(OpenAccount.resource_id)
    )
    tabs = {row[0]: (int(row[1]), float(row[2]), row[3]) for row in tabs_result.all()}

    bookings_result = await db.execute(
        select(Booking)
        .where(
            Booking.company_id == company_id,
            Booking.resource_id.in_(resource_ids),
            Booking.status.in_(_ACTIVE_BOOKING_STATUSES),
            Booking.starts_at < horizon,
            Booking.ends_at > now,
        )
        .order_by(Booking.starts_at)
    )
    soonest_booking: dict[uuid.UUID, Booking] = {}
    for booking in bookings_result.scalars().all():
        soonest_booking.setdefault(booking.resource_id, booking)

    rows = []
    for resource in resources:
        open_accounts, open_total, opened_at = tabs.get(resource.id, (0, 0.0, None))
        booking = soonest_booking.get(resource.id)
        if open_accounts > 0:
            status = STATUS_OCUPADA
        elif booking is not None:
            status = STATUS_RESERVADA
        else:
            status = STATUS_LIVRE
        rows.append({
            "resource_id": resource.id,
            "name": resource.name,
            "capacity": resource.capacity,
            "status": status,
            "open_accounts": open_accounts,
            "open_total": open_total,
            "opened_at": opened_at,
            "booking_id": booking.id if booking else None,
            "booking_starts_at": booking.starts_at if booking else None,
            "booking_ends_at": booking.ends_at if booking else None,
            "booking_status": booking.status.value if booking else None,
        })
    return rows
