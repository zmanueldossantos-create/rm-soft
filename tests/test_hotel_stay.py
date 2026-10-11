"""Hotel stay (point 2, part A): the room rate charged as long as the stay lasts, the money only at the till
(closing the stay's account concludes the booking), the check-out only for a stay with nothing to pay, the
extension of a stay in progress, and no manual status change that would free a room with an unpaid account."""
import uuid
from datetime import datetime, timedelta

import pytest

from app.models.booking import BookingStatus
from app.models.open_account import OpenAccountStatus
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services.booking_service import (
    BookingNotEditableError, BookingOverlapError, create_booking, list_bookings, update_booking_status,
)
from app.services.cash_session_service import open_session
from app.services.hotel_service import (
    LUANDA, InvalidStayStateError, StayHasUnpaidAccountError, check_in, check_out, extend_stay,
)
from app.schemas.booking import BookingResponse
from app.services.open_account_service import (
    InvalidLineError, InvalidTransferError, add_line, close_account, list_account_lines, open_account, remove_line,
    transfer_lines, update_line_quantity,
)

# Tomorrow 14:00 in Luanda - the usual check-in hour, away from midnight.
BASE = (datetime.now(LUANDA) + timedelta(days=1)).replace(hour=14, minute=0, second=0, microsecond=0)


async def _hotel(db, ctx, requires_service=True):
    """A room type, one room, and two rates: the night (no duration) and the hour (60 min)."""
    company_id = ctx["company"].id
    room_type = ResourceTypeCatalog(company_id=company_id, name="Quarto", requires_service=requires_service)
    db.add(room_type)
    await db.flush()
    room = Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=room_type.id, name="Quarto 101")
    night = Service(company_id=company_id, code="HTL-DIA", name="Diária", price=25000, vat_id=ctx["vat_nor"].id,
                    unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room_type.id)
    hour = Service(company_id=company_id, code="HTL-1H", name="Quarto 1 hora", price=5000, vat_id=ctx["vat_nor"].id,
                   unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room_type.id, duration_minutes=60)
    db.add_all([room, night, hour])
    await db.commit()
    return room, night, hour


async def _stay(db, ctx, room, service, starts_at, ends_at):
    """A booking checked in - returns (booking, account, quantity of its room-rate line)."""
    booking = await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id, starts_at, ends_at,
                                   service_id=service.id if service else None)
    booking, account = await check_in(db, ctx["company"].id, booking.id, ctx["gestor"])
    lines = await list_account_lines(db, account.id)
    return booking, account, (float(lines[0].quantity) if lines else None)


@pytest.mark.asyncio
async def test_the_night_rate_is_charged_once_per_night(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    _, _, quantity = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=2, hours=-2))  # 14:00 -> 2 days later 12:00
    assert quantity == 2


@pytest.mark.asyncio
async def test_a_short_stay_on_the_night_rate_is_one_night(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    _, _, quantity = await _stay(db, ctx, room, night, BASE, BASE + timedelta(hours=1))
    assert quantity == 1


@pytest.mark.asyncio
async def test_a_timed_rate_is_charged_per_started_slice(db, company_with_essentials):
    ctx = company_with_essentials
    room, _, hour = await _hotel(db, ctx)
    _, _, quantity = await _stay(db, ctx, room, hour, BASE, BASE + timedelta(hours=2, minutes=30))
    assert quantity == 3


@pytest.mark.asyncio
async def test_check_out_is_refused_while_the_account_has_something_to_pay(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking, account, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    with pytest.raises(StayHasUnpaidAccountError, match="Caixa"):
        await check_out(db, ctx["company"].id, booking.id)
    await db.refresh(booking)
    await db.refresh(account)
    assert booking.status == BookingStatus.EM_CURSO
    assert account.status == OpenAccountStatus.ABERTA


@pytest.mark.asyncio
async def test_check_out_of_a_stay_with_nothing_to_pay(db, company_with_essentials):
    ctx = company_with_essentials
    room, _, _ = await _hotel(db, ctx, requires_service=False)
    booking, account, quantity = await _stay(db, ctx, room, None, BASE, BASE + timedelta(days=1))
    assert quantity is None  # no rate, no line
    booking = await check_out(db, ctx["company"].id, booking.id)
    await db.refresh(account)
    assert booking.status == BookingStatus.CONCLUIDA
    assert account.status == OpenAccountStatus.FECHADA
    assert account.invoice_id is None
    with pytest.raises(InvalidStayStateError):
        await check_out(db, ctx["company"].id, booking.id)


@pytest.mark.asyncio
async def test_paying_the_stay_at_the_till_concludes_the_booking(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], 0)
    booking, account, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    account = await close_account(db, ctx["company"].id, account.id, ctx["gestor"],
                                  [{"payment_method_id": ctx["pm_numerario"].id, "amount": 28500.0}])  # 25 000 + 14 %
    await db.refresh(booking)
    assert account.invoice_id is not None
    assert booking.status == BookingStatus.CONCLUIDA


@pytest.mark.asyncio
async def test_extending_a_stay_recomputes_its_room_rate_line(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking, account, quantity = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    assert quantity == 1
    booking = await extend_stay(db, ctx["company"].id, booking.id, (BASE + timedelta(days=3)).replace(tzinfo=None))  # as the screen sends it
    lines = await list_account_lines(db, account.id)
    assert float(lines[0].quantity) == 3
    assert booking.ends_at == BASE + timedelta(days=3)


@pytest.mark.asyncio
async def test_a_stay_cannot_be_extended_over_the_next_booking(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking, _, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id,
                         BASE + timedelta(days=2), BASE + timedelta(days=3), service_id=night.id)
    with pytest.raises(BookingOverlapError):
        await extend_stay(db, ctx["company"].id, booking.id, BASE + timedelta(days=2, hours=2))


@pytest.mark.asyncio
async def test_no_manual_status_change_frees_a_room_with_an_unpaid_account(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking, _, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    with pytest.raises(BookingNotEditableError):
        await update_booking_status(db, ctx["company"].id, booking.id, BookingStatus.CONCLUIDA)
    await db.refresh(booking)
    assert booking.status == BookingStatus.EM_CURSO


@pytest.mark.asyncio
async def test_only_a_pending_or_confirmed_booking_checks_in(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking = await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id, BASE, BASE + timedelta(days=1),
                                   service_id=night.id)
    await update_booking_status(db, ctx["company"].id, booking.id, BookingStatus.CANCELADA)
    with pytest.raises(InvalidStayStateError):
        await check_in(db, ctx["company"].id, booking.id, ctx["gestor"])


@pytest.mark.asyncio
async def test_a_room_account_opens_only_at_check_in(db, company_with_essentials):
    """Opening a bare tab on a room would skip the booking and its rate: refused. A table still opens one."""
    ctx = company_with_essentials
    room, _, _ = await _hotel(db, ctx)
    with pytest.raises(InvalidLineError, match="check-in"):
        await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Quarto 101",
                           resource_id=room.id)
    table_type = ResourceTypeCatalog(company_id=ctx["company"].id, name="Mesa")
    db.add(table_type)
    await db.flush()
    table = Resource(company_id=ctx["company"].id, activity_id=ctx["activity"].id, resource_type_id=table_type.id, name="Mesa 1")
    db.add(table)
    await db.commit()
    account = await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Mesa 1",
                                 resource_id=table.id)
    assert account.status == OpenAccountStatus.ABERTA


@pytest.mark.asyncio
async def test_lines_are_never_moved_onto_a_room(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    tab = await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Balcão")
    line = await add_line(db, ctx["company"].id, tab.id, ctx["gestor"].id, 1, service_id=night.id)
    with pytest.raises(InvalidTransferError, match="check-in"):
        await transfer_lines(db, ctx["company"].id, tab.id, ctx["gestor"].id, [{"line_id": line.id, "quantity": 1}],
                             target_resource_id=room.id)


@pytest.mark.asyncio
async def test_a_stay_in_progress_is_listed_whatever_the_dates(db, company_with_essentials):
    """The guest is still in the room after the planned end: the day's list keeps showing the stay."""
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    late, _, _ = await _stay(db, ctx, room, night, BASE - timedelta(days=4), BASE - timedelta(days=3))
    done = await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id,
                                BASE - timedelta(days=6), BASE - timedelta(days=5), service_id=night.id)
    listed = await list_bookings(db, ctx["company"].id, date_from=BASE, date_to=BASE + timedelta(days=1))
    assert [b.id for b in listed] == [late.id]
    assert done.id not in [b.id for b in listed]


@pytest.mark.asyncio
async def test_the_room_rate_line_follows_the_stay_never_a_hand(db, company_with_essentials):
    """A 3-night stay can never be cashed as one: the room-rate line is not raised, lowered, removed or re-added by
    hand - only the stay's dates move it (extend_stay). Other lines stay free."""
    ctx = company_with_essentials
    cid, uid = ctx["company"].id, ctx["gestor"].id
    room, night, hour = await _hotel(db, ctx)
    _, account, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=3))
    rate_line = (await list_account_lines(db, account.id))[0]
    assert rate_line.is_stay_rate is True
    with pytest.raises(InvalidLineError, match="Prolongar"):
        await update_line_quantity(db, cid, account.id, rate_line.id, 1)
    with pytest.raises(InvalidLineError, match="Prolongar"):
        await remove_line(db, cid, account.id, rate_line.id)
    with pytest.raises(InvalidLineError, match="Prolongar"):
        await add_line(db, cid, account.id, uid, 1, service_id=night.id)
    extra = await add_line(db, cid, account.id, uid, 1, service_id=hour.id)  # another service is a normal extra
    assert float((await update_line_quantity(db, cid, account.id, extra.id, 2)).quantity) == 2
    lines = await list_account_lines(db, account.id)
    assert [float(l.quantity) for l in lines if l.is_stay_rate] == [3]


@pytest.mark.asyncio
async def test_a_listed_stay_carries_its_account_and_what_is_due(db, company_with_essentials):
    ctx = company_with_essentials
    room, night, _ = await _hotel(db, ctx)
    booking, account, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=1))
    waiting = await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id,
                                   BASE + timedelta(days=2), BASE + timedelta(days=3), service_id=night.id)
    listed = {b.id: b for b in await list_bookings(db, ctx["company"].id)}
    assert listed[booking.id].stay_account_id == account.id
    assert listed[booking.id].stay_account_total == 28500.0  # 25 000 + 14 %
    assert listed[waiting.id].stay_account_id is None


def test_a_booking_returned_outside_the_listing_answers_with_the_defaults():
    """Creation, check-in... return a Booking without the listing's extra attributes: the response still builds."""
    from types import SimpleNamespace
    now = datetime.now(LUANDA)
    booking = SimpleNamespace(
        id=uuid.uuid4(), company_id=uuid.uuid4(), resource_id=uuid.uuid4(), customer_id=None, service_id=None,
        starts_at=now, ends_at=now, status="PENDENTE", notes=None, guest_name=None, party_size=None,
        created_by_user_id=uuid.uuid4(), created_at=now,
    )
    response = BookingResponse.model_validate(booking)
    assert response.stay_account_id is None and response.stay_account_total is None
