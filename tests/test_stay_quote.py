"""Nova reserva - the price shown before booking: the same count and price as the check-in (nights, slices of a
timed rate, periods of a rate with its own hours), at the room's own price when it has one; excluding VAT."""
from datetime import time, timedelta

import pytest

from app.models.service import Service
from app.services.hotel_service import stay_quote
from app.services.resource_service import set_rate_prices
from tests.test_hotel_stay import BASE, _hotel


@pytest.mark.asyncio
async def test_the_price_before_booking(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, night, hour = await _hotel(db, ctx)
    overnight = Service(company_id=cid, code="HTL-PER", name="Pernoite", price=10000, vat_id=ctx["vat_nor"].id,
                        unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room.resource_type_id,
                        stay_start_time=time(22, 0), stay_end_time=time(7, 30))
    db.add(overnight)
    await db.commit()

    q = await stay_quote(db, cid, room.id, night.id, BASE, BASE + timedelta(days=2))
    assert (q["quantity"], q["unit"], q["unit_price"], q["total"], q["own_price"]) == (2, "NOITE", 25000.0, 50000.0, False)
    assert q["vat_rate"] == 14.0

    q = await stay_quote(db, cid, room.id, hour.id, BASE, BASE + timedelta(hours=2, minutes=10))
    assert (q["quantity"], q["unit"], q["total"]) == (3, "FATIA", 15000.0)  # 3 started slices of 60 min

    start = BASE.replace(hour=22)
    q = await stay_quote(db, cid, room.id, overnight.id, start, start + timedelta(hours=9, minutes=30))
    assert (q["quantity"], q["unit"], q["total"]) == (1, "PERIODO", 10000.0)

    await set_rate_prices(db, cid, room.id, [{"service_id": night.id, "price": 30000}])
    q = await stay_quote(db, cid, room.id, night.id, BASE.replace(tzinfo=None), (BASE + timedelta(days=3)).replace(tzinfo=None))
    assert (q["quantity"], q["unit_price"], q["total"], q["own_price"]) == (3, 30000.0, 90000.0, True)  # Luanda's hours
