"""
Hotel-specific service layer - check-in/check-out actions that combine the
two generic building blocks (Booking for the reservation, OpenAccount for the
running tab of extras) into the hotel stay workflow. See the road-map
discussion: Hotel = Booking (multi-night reservation, already supported
unchanged by Booking.starts_at/ends_at) + OpenAccount (room extras until
check-out), glued together here rather than as a third generic concept.

check_in: transitions the Booking to EM_CURSO, opens an OpenAccount for the
room (labeled with the room's name) linked back to the booking via
OpenAccount.booking_id, and - if the booking has a service (the nightly rate,
e.g. "Diaria Quarto Standard") - adds one line for that rate multiplied by the
number of nights, so the guest's bill already reflects the room charge before
any extras are added.

check_out: closes the OpenAccount (via open_account_service.close_account,
producing the consolidated invoice - room charge + all extras, in the exact
same pipeline as every other sale) and marks the Booking CONCLUIDA.

Room status (Livre/Ocupado) is deliberately NOT stored anywhere - it's derived
on demand from whether a resource currently has an EM_CURSO booking, computed
by whoever renders the room list (avoids a second source of truth to keep in
sync with Booking.status).
"""
import uuid
from datetime import datetime, date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.point_of_sale import PointOfSale
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.service import Service
from app.models.resource import Resource
from app.models.customer import Customer
from app.models.invoice import Invoice
from app.services.booking_service import get_booking_or_raise
from app.services.resource_service import get_resource_or_raise
from app.services.open_account_service import open_account, add_line, close_account


class NoDefaultPosError(Exception):
    pass


class AmbiguousOpenSessionError(Exception):
    pass


class AlreadyCheckedInError(Exception):
    pass


def _nights_between(starts_at: datetime, ends_at: datetime) -> int:
    nights = (ends_at.date() - starts_at.date()).days
    return max(nights, 1)


async def check_in(
    db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, checking_in_user: "User",
    pos_id: uuid.UUID | None = None,
) -> tuple[Booking, OpenAccount]:
    """pos_id lets the caller pick which of the activity's POS to bill the stay
    through (e.g. a dedicated reception till instead of the activity's auto-created
    default one) - falls back to the default POS when not given, but the caller
    is responsible for making sure THAT POS has an open cash session (see
    pos_service.checkout's NoOpenSessionError) - explicit choice avoids silently
    targeting a closed default till when a different POS was actually opened.
    """
    booking = await get_booking_or_raise(db, company_id, booking_id)
    if booking.status == BookingStatus.EM_CURSO:
        raise AlreadyCheckedInError("Esta reserva ja tem check-in efetuado")

    resource = await get_resource_or_raise(db, company_id, booking.resource_id)

    if pos_id is not None:
        pos_result = await db.execute(
            select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.activity_id == resource.activity_id)
        )
        pos = pos_result.scalar_one_or_none()
        if pos is None:
            raise NoDefaultPosError("Ponto de venda nao encontrado para esta atividade")
    else:
        # No explicit pos_id - find whichever of this activity's POS currently has
        # an open cash session (normal case: one cashier active at a time), rather
        # than blindly targeting the activity's auto-created "default" POS, which
        # may not be the one actually in use (see the "caixa geral sempre fechada"
        # discussion - a GESTOR opened a different, non-default POS instead).
        open_pos_result = await db.execute(
            select(PointOfSale)
            .join(CashSession, CashSession.pos_id == PointOfSale.id)
            .where(PointOfSale.activity_id == resource.activity_id, CashSession.status == CashSessionStatus.ABERTA)
        )
        open_pos_list = list(open_pos_result.scalars().all())
        if len(open_pos_list) == 1:
            pos = open_pos_list[0]
        elif len(open_pos_list) > 1:
            raise AmbiguousOpenSessionError("Existe mais de uma caixa aberta nesta atividade - indique qual usar")
        else:
            default_result = await db.execute(
                select(PointOfSale).where(PointOfSale.activity_id == resource.activity_id, PointOfSale.is_default == True)  # noqa: E712
            )
            pos = default_result.scalar_one_or_none()
            if pos is None:
                raise NoDefaultPosError("Ponto de venda nao encontrado para esta atividade")

    account = await open_account(
        db, company_id, resource.activity_id, pos.id, checking_in_user.id,
        label=resource.name, resource_id=resource.id, customer_id=booking.customer_id,
    )
    account.booking_id = booking.id
    await db.commit()
    await db.refresh(account)

    if booking.service_id is not None:
        service_result = await db.execute(select(Service).where(Service.id == booking.service_id))
        service = service_result.scalar_one_or_none()
        if service is not None and service.price is not None:
            nights = _nights_between(booking.starts_at, booking.ends_at)
            await add_line(db, company_id, account.id, checking_in_user.id, quantity=nights, service_id=service.id)

    booking.status = BookingStatus.EM_CURSO
    await db.commit()
    await db.refresh(booking)
    await db.refresh(account)

    return booking, account


async def check_out(
    db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, checking_out_user: "User", payments: list[dict],
) -> Booking:
    booking = await get_booking_or_raise(db, company_id, booking_id)

    account_result = await db.execute(
        select(OpenAccount).where(OpenAccount.booking_id == booking_id, OpenAccount.status == OpenAccountStatus.ABERTA)
    )
    account = account_result.scalar_one_or_none()
    if account is not None:
        await close_account(db, company_id, account.id, checking_out_user, payments)

    booking.status = BookingStatus.CONCLUIDA
    await db.commit()
    await db.refresh(booking)
    return booking


async def get_occupancy_history(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None,
    date_from: datetime | None = None, date_to: datetime | None = None,
) -> list[dict]:
    """Past and current stays (CONCLUIDA and EM_CURSO bookings) with the room
    name, guest, dates and the resulting invoice total when the stay has been
    checked out - purely a read/aggregation over existing data (Booking,
    Resource, OpenAccount, Invoice, Customer), no new storage of its own. See the
    Hotel road-map: "Historico das ocupacoes" (point 6).
    """
    query = (
        select(Booking, Resource.name.label("resource_name"), Customer.name.label("customer_name"),
               Invoice.series, Invoice.number, Invoice.total)
        .join(Resource, Resource.id == Booking.resource_id)
        .outerjoin(Customer, Customer.id == Booking.customer_id)
        .outerjoin(OpenAccount, OpenAccount.booking_id == Booking.id)
        .outerjoin(Invoice, Invoice.id == OpenAccount.invoice_id)
        .where(Booking.company_id == company_id, Booking.status.in_([BookingStatus.CONCLUIDA, BookingStatus.EM_CURSO]))
        .order_by(Booking.starts_at.desc())
    )
    if activity_id is not None:
        query = query.where(Resource.activity_id == activity_id)
    if date_from is not None:
        query = query.where(Booking.starts_at >= date_from)
    if date_to is not None:
        query = query.where(Booking.starts_at <= date_to)

    result = await db.execute(query)
    rows = result.all()
    return [
        {
            "booking_id": booking.id,
            "resource_name": resource_name,
            "customer_name": customer_name,
            "starts_at": booking.starts_at,
            "ends_at": booking.ends_at,
            "status": booking.status,
            "invoice_series": series,
            "invoice_number": number,
            "invoice_total": float(total) if total is not None else None,
        }
        for booking, resource_name, customer_name, series, number, total in rows
    ]
