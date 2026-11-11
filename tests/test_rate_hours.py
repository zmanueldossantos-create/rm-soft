"""Reservas - a rate with hours of its own (Pernoite 22:00 -> 07:30, Day use 08:00 -> 18:00): set on the rate of a
resource type, never with a duration; charged once per period (overnight hours per night, same-day hours per day);
a Pernoite can be taken on arrival (a passage ending at 07:30 the next morning)."""
from datetime import datetime, time, timedelta, timezone

import pytest

from app.models.service import Service
from app.services.hotel_service import LUANDA, _stay_quantity, stay_end_from
from app.services.service_service import InvalidStayHoursError, check_stay_hours
from tests.test_hotel_walk_in import _enter, _rooms


def test_the_hours_of_a_rate_are_checked():
    check_stay_hours("type", None, time(22), time(7, 30))
    check_stay_hours(None, 60, None, None)
    with pytest.raises(InvalidStayHoursError, match="ou nenhuma"):
        check_stay_hours("type", None, time(22), None)
    with pytest.raises(InvalidStayHoursError, match="tipo de recurso"):
        check_stay_hours(None, None, time(22), time(7, 30))
    with pytest.raises(InvalidStayHoursError, match="não os dois"):
        check_stay_hours("type", 60, time(22), time(7, 30))
    with pytest.raises(InvalidStayHoursError, match="diferente"):
        check_stay_hours("type", None, time(12), time(12))


def test_a_rate_with_hours_is_charged_once_per_period():
    pernoite = Service(stay_start_time=time(22), stay_end_time=time(7, 30))
    day_use = Service(stay_start_time=time(8), stay_end_time=time(18))
    night = Service()
    start = datetime(2026, 11, 10, 22, 0, tzinfo=LUANDA)
    assert _stay_quantity(pernoite, start, start + timedelta(hours=9, minutes=30)) == 1
    assert _stay_quantity(pernoite, start, start + timedelta(days=2, hours=9, minutes=30)) == 3  # three nights
    morning = datetime(2026, 11, 10, 8, 0, tzinfo=LUANDA)
    assert _stay_quantity(day_use, morning, morning + timedelta(hours=10)) == 1
    assert _stay_quantity(day_use, morning, morning + timedelta(days=1, hours=10)) == 2  # two days
    assert _stay_quantity(night, start, start + timedelta(hours=14)) == 1
    # taken at 22:30: until 07:30 the next morning; at 03:00: until 07:30 the same morning
    assert stay_end_from(pernoite, datetime(2026, 11, 10, 22, 30, tzinfo=LUANDA)) == datetime(2026, 11, 11, 7, 30, tzinfo=LUANDA)
    assert stay_end_from(pernoite, datetime(2026, 11, 11, 3, 0, tzinfo=LUANDA)) == datetime(2026, 11, 11, 7, 30, tzinfo=LUANDA)
    assert stay_end_from(night, start) is None


@pytest.mark.asyncio
async def test_a_pernoite_taken_on_arrival(db, company_with_essentials):
    ctx = company_with_essentials
    room, hour, _night = await _rooms(db, ctx)
    pernoite = Service(company_id=ctx["company"].id, code="PAS-PER", name="Pernoite", price=10000,
                       vat_id=ctx["vat_nor"].id, unit_of_measure_id=ctx["unit_un"].id,
                       resource_type_id=hour.resource_type_id, stay_start_time=time(22), stay_end_time=time(7, 30))
    db.add(pernoite)
    await db.commit()
    now = datetime.now(timezone.utc)
    booking, invoice = await _enter(db, ctx, room, pernoite, now=now, amount=11400.0)
    assert float(invoice.total) == 11400.0
    end = booking.ends_at.astimezone(LUANDA)
    assert (end.hour, end.minute) == (7, 30) and timedelta(0) < booking.ends_at - now <= timedelta(days=1)
