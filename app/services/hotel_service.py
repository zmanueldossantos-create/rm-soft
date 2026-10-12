"""
Hotel-specific service layer - check-in/check-out actions that combine the
two generic building blocks (Booking for the reservation, OpenAccount for the
running tab of extras) into the hotel stay workflow. See the road-map
discussion: Hotel = Booking (multi-night reservation, already supported
unchanged by Booking.starts_at/ends_at) + OpenAccount (room extras until
check-out), glued together here rather than as a third generic concept.

check_in: transitions the Booking to EM_CURSO, opens an OpenAccount for the
room (labeled with the room's name) linked back to the booking via
OpenAccount.booking_id, and - if the booking has a service (the rate, e.g.
"Diaria Quarto Standard" or "Quarto 1 hora") - adds one line for that rate,
charged as many times as the stay lasts (see _stay_quantity), so the guest's
bill already reflects the room charge before any extras are added.

The money of a stay is cashed at the till, never here: closing the stay's
account (open_account_service.close_account, the same pipeline as every other
sale) concludes the booking. check_out only ends a stay with nothing left to
pay (an account without articles, or none at all).

extend_stay: moves the end of a stay in progress (the guest stays longer, or
leaves earlier) and recomputes the room-rate line of its account.

The history of the rooms (stays, passages, revenue) is resource_history_service, common to every sector.

Room status (Livre/Ocupado) is deliberately NOT stored anywhere - it's derived
on demand from whether a resource currently has an EM_CURSO booking, computed
by whoever renders the room list (avoids a second source of truth to keep in
sync with Booking.status).
"""
import math
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.booking import Booking, BookingStatus
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.point_of_sale import PointOfSale
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.service import Service
from app.models.invoice import Invoice
from app.services.booking_service import (
    get_booking_or_raise, _clean_guest_name, _has_overlap, _validate_service_for_resource,
    BookingOverlapError, InvalidBookingRangeError,
)
from app.services.document_rules import default_paid_on_issue_type
from app.services.pos_service import checkout
from app.services.stay_text import stay_observation
from app.services.resource_service import get_resource_or_raise
from app.services.open_account_service import open_account, add_line, KITCHEN_CANCELLED

# Angola has a single time zone, UTC+1, without daylight saving: a night is counted on Luanda's calendar.
LUANDA = timezone(timedelta(hours=1))


class NoDefaultPosError(Exception):
    pass


class AmbiguousOpenSessionError(Exception):
    pass


class AlreadyCheckedInError(Exception):
    pass


class InvalidStayStateError(Exception):
    """The booking is not in the state the action needs (check-in of a cancelled booking, check-out of a stay
    that never started...)."""


class StayHasUnpaidAccountError(Exception):
    """The stay's account still holds articles: it is paid at the till, which concludes the booking."""


class InvalidWalkInError(Exception):
    """A passage needs an active service with a duration (30 min, 1 hora...)."""


def _nights_between(starts_at: datetime, ends_at: datetime) -> int:
    """Nights between two moments, on Luanda's calendar - at least one (a short stay is charged one night)."""
    nights = (ends_at.astimezone(LUANDA).date() - starts_at.astimezone(LUANDA).date()).days
    return max(nights, 1)


def _stay_quantity(service: Service, starts_at: datetime, ends_at: datetime) -> int:
    """How many times the booked rate is charged: a timed rate ("Quarto 1 hora", duration 60 min) once per started
    slice of its duration - 2h30 on a 1-hour rate is 3; a rate without duration (the night) once per night."""
    if service.duration_minutes:
        minutes = (ends_at - starts_at).total_seconds() / 60
        return max(math.ceil(minutes / service.duration_minutes - 1e-9), 1)
    return _nights_between(starts_at, ends_at)


async def _open_stay_account(db: AsyncSession, booking_id: uuid.UUID) -> OpenAccount | None:
    return (await db.execute(
        select(OpenAccount).where(OpenAccount.booking_id == booking_id, OpenAccount.status == OpenAccountStatus.ABERTA)
    )).scalar_one_or_none()


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
        raise AlreadyCheckedInError("Esta reserva já tem check-in efetuado")
    if booking.status not in (BookingStatus.PENDENTE, BookingStatus.CONFIRMADA):
        raise InvalidStayStateError("Só uma reserva pendente ou confirmada pode fazer check-in")

    resource = await get_resource_or_raise(db, company_id, booking.resource_id)

    if pos_id is not None:
        pos_result = await db.execute(
            select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.activity_id == resource.activity_id)
        )
        pos = pos_result.scalar_one_or_none()
        if pos is None:
            raise NoDefaultPosError("Ponto de venda não encontrado para esta atividade")
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
                raise NoDefaultPosError("Ponto de venda não encontrado para esta atividade")

    account = await open_account(
        db, company_id, resource.activity_id, pos.id, checking_in_user.id,
        label=resource.name, resource_id=resource.id, customer_id=booking.customer_id, booking_id=booking.id,
    )

    if booking.service_id is not None:
        service_result = await db.execute(select(Service).where(Service.id == booking.service_id))
        service = service_result.scalar_one_or_none()
        if service is not None and service.price is not None:
            quantity = _stay_quantity(service, booking.starts_at, booking.ends_at)
            await add_line(db, company_id, account.id, checking_in_user.id, quantity=quantity, service_id=service.id,
                           stay_rate=True)

    booking.status = BookingStatus.EM_CURSO
    await db.commit()
    await db.refresh(booking)
    await db.refresh(account)

    return booking, account


async def check_out(db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID) -> Booking:
    """Ends a stay with nothing left to pay. A stay whose account holds articles is paid at the till - closing
    that account concludes the booking (open_account_service.close_account) - so it is refused here: no money
    ever leaves this path without a payment. An account without articles is closed without any document."""
    booking = await get_booking_or_raise(db, company_id, booking_id)
    if booking.status != BookingStatus.EM_CURSO:
        raise InvalidStayStateError("Esta reserva não está em curso")

    account = await _open_stay_account(db, booking.id)
    if account is not None:
        articles = (await db.execute(
            select(func.count()).select_from(OpenAccountLine).where(
                OpenAccountLine.account_id == account.id, OpenAccountLine.kitchen_status.is_distinct_from(KITCHEN_CANCELLED),
            )
        )).scalar_one()
        if articles:
            raise StayHasUnpaidAccountError("A estadia tem uma conta por pagar - o check-out faz-se na Caixa, com o pagamento")
        account.status = OpenAccountStatus.FECHADA
        account.closed_at = func.now()

    booking.status = BookingStatus.CONCLUIDA
    booking.checked_out_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(booking)
    return booking


async def walk_in(
    db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID, service_id: uuid.UUID, selling_user: "User",
    pos_id: uuid.UUID, payments: list[dict], customer_id: uuid.UUID | None = None,
    guest_name: str | None = None, party_size: int | None = None, now: datetime | None = None,
) -> tuple[Booking, Invoice]:
    """A passage (30 min, 1 hora, 2 horas...), paid before going in. Everything is checked first - the room free
    for the whole duration and not still occupied, a timed service of its type, a till of its activity - so nothing is
    ever cashed for a room the guest cannot have. The sale is an ordinary till sale (pos_service.checkout: series,
    VAT, payments, session), then the room is occupied from now for the service's duration, the booking linked to
    its invoice. Its exit (check_out) has nothing left to pay."""
    resource = await get_resource_or_raise(db, company_id, resource_id)
    service = (await db.execute(
        select(Service).where(Service.id == service_id, Service.company_id == company_id)
    )).scalar_one_or_none()
    if service is None or not service.is_active:
        raise InvalidWalkInError("Serviço não encontrado ou inativo")
    if not service.duration_minutes:
        raise InvalidWalkInError("Uma entrada imediata precisa de um serviço com duração (30 min, 1 hora...) - uma diária faz-se por reserva")
    await _validate_service_for_resource(db, company_id, resource, service.id)
    pos = (await db.execute(
        select(PointOfSale).where(PointOfSale.id == pos_id, PointOfSale.activity_id == resource.activity_id)
    )).scalar_one_or_none()
    if pos is None:
        raise NoDefaultPosError("Este ponto de venda não pertence à atividade do quarto")

    starts_at = now or datetime.now(timezone.utc)
    ends_at = starts_at + timedelta(minutes=service.duration_minutes)
    still_occupied = (await db.execute(
        select(Booking.id).where(Booking.resource_id == resource.id, Booking.status == BookingStatus.EM_CURSO).limit(1)
    )).first()
    if still_occupied is not None:
        raise BookingOverlapError(f"{resource.name} ainda está ocupado - registe a saída antes de uma nova entrada")
    if await _has_overlap(db, resource.id, starts_at, ends_at):
        raise BookingOverlapError(f"{resource.name} tem uma reserva neste período")

    invoice = await checkout(
        db, company_id, pos.id, selling_user, customer_id,
        [{"product_id": None, "service_id": str(service.id), "quantity": 1.0, "sale_unit_id": None}],
        payments, invoice_type=await default_paid_on_issue_type(db), stay_sale=True,
        observations=stay_observation(resource.name, starts_at, ends_at, _clean_guest_name(guest_name), party_size),
    )
    booking = Booking(
        company_id=company_id, resource_id=resource.id, customer_id=customer_id, service_id=service.id,
        starts_at=starts_at, ends_at=ends_at, status=BookingStatus.EM_CURSO, created_by_user_id=selling_user.id,
        guest_name=_clean_guest_name(guest_name), party_size=party_size, invoice_id=invoice.id,
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking, invoice


async def extend_stay(db: AsyncSession, company_id: uuid.UUID, booking_id: uuid.UUID, ends_at: datetime) -> Booking:
    """Moves the end of a stay in progress - the guest stays longer, or leaves earlier - and recomputes the
    room-rate line of its account with the same rule as at check-in, so the bill always matches the stay.
    (reschedule_booking refuses a stay in progress: it would change the dates without the bill.)"""
    if ends_at.tzinfo is None:  # the screen sends Luanda wall-clock time, as for every booking
        ends_at = ends_at.replace(tzinfo=LUANDA)
    booking = await get_booking_or_raise(db, company_id, booking_id)
    if booking.status != BookingStatus.EM_CURSO:
        raise InvalidStayStateError("Só uma estadia em curso pode ser prolongada")
    if ends_at <= booking.starts_at:
        raise InvalidBookingRangeError("A data/hora de fim deve ser posterior ao início")
    if await _has_overlap(db, booking.resource_id, booking.starts_at, ends_at, exclude_booking_id=booking.id):
        raise BookingOverlapError("Este recurso já tem uma reserva neste período")

    booking.ends_at = ends_at
    account = await _open_stay_account(db, booking.id)
    if account is not None and booking.service_id is not None:
        service = (await db.execute(select(Service).where(Service.id == booking.service_id))).scalar_one_or_none()
        line = (await db.execute(
            select(OpenAccountLine).where(
                OpenAccountLine.account_id == account.id, OpenAccountLine.service_id == booking.service_id,
            ).order_by(OpenAccountLine.added_at).limit(1)
        )).scalars().first()
        if service is not None and line is not None:
            line.quantity = _stay_quantity(service, booking.starts_at, ends_at)

    await db.commit()
    await db.refresh(booking)
    return booking
