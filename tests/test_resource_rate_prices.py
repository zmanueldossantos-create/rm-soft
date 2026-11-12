"""Recursos - a resource's own price for a rate of its type (the Luanda room's 1 hora at 8 000 where the type says
5 000): used at the check-in, on a passage, everywhere the rate is sold with that resource; the others keep the
rate's price. Only a rate of the resource's type; an empty price is the rate's own."""
from datetime import timedelta

import pytest

from app.models.resource import Resource
from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.open_account_service import list_account_lines
from app.services.resource_service import InvalidRatePriceError, attach_rate_prices, set_rate_prices
from tests.test_hotel_stay import BASE, _hotel, _stay
from tests.test_hotel_walk_in import _enter


@pytest.mark.asyncio
async def test_a_room_with_its_own_price(db, company_with_essentials):
    ctx = company_with_essentials
    cid = ctx["company"].id
    room, night, hour = await _hotel(db, ctx)
    other = Resource(company_id=cid, activity_id=ctx["activity"].id, resource_type_id=room.resource_type_id, name="Quarto 102")
    foreign = Service(company_id=cid, code="SPA-1", name="Massagem", price=9000, vat_id=ctx["vat_nor"].id,
                      unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([other, foreign])
    await db.commit()

    room = await set_rate_prices(db, cid, room.id, [{"service_id": night.id, "price": 30000}, {"service_id": hour.id, "price": None}])
    assert room.rate_prices == {night.id: 30000.0}  # the empty one: the rate's own price
    with pytest.raises(InvalidRatePriceError, match="tipo deste recurso"):
        await set_rate_prices(db, cid, room.id, [{"service_id": foreign.id, "price": 1000}])
    with pytest.raises(InvalidRatePriceError, match="negativo"):
        await set_rate_prices(db, cid, room.id, [{"service_id": night.id, "price": -1}])

    _, account, _ = await _stay(db, ctx, room, night, BASE, BASE + timedelta(days=2, hours=-2))
    [line] = await list_account_lines(db, account.id)
    assert (float(line.quantity), float(line.unit_price)) == (2.0, 30000.0)  # 2 nights at the room's own price
    _, account, _ = await _stay(db, ctx, other, night, BASE, BASE + timedelta(days=1, hours=-2))
    [line] = await list_account_lines(db, account.id)
    assert float(line.unit_price) == 25000.0  # the other room: the rate's price

    await set_rate_prices(db, cid, other.id, [{"service_id": hour.id, "price": 8000}])
    # a passage on a free room with its own 1 hora
    await open_session(db, cid, ctx["pos"].id, ctx["gestor"], 0)
    assert (await attach_rate_prices(db, [other]))[0].rate_prices == {hour.id: 8000.0}
    room3 = Resource(company_id=cid, activity_id=ctx["activity"].id, resource_type_id=room.resource_type_id, name="Quarto 103")
    db.add(room3)
    await db.commit()
    await set_rate_prices(db, cid, room3.id, [{"service_id": hour.id, "price": 8000}])
    _booking, invoice = await _enter(db, ctx, room3, hour, amount=9120.0)  # 8 000 + 14 %
    assert float(invoice.total) == 9120.0
