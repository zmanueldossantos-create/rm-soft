"""
API pública, step 4: bookings. The hotel's site sees what is free per room type with its rates and the price of the
stay, books a type (RM SOFT gives a free room) - PENDENTE, the reception confirms - follows and cancels its own
bookings before the check-in. Idempotent; the last room cannot be given twice; the gestor is told.
"""
import contextlib
import uuid
from datetime import date, time, timedelta

import httpx
import pytest
from sqlalchemy import func, select

from app.core.database import get_db
from app.main import app
from app.models.booking import Booking, BookingStatus
from app.models.notification import NotificationOutbox, NotificationRecipient
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services import api_key_service as keys

API = "/api/public/v1"
IN = date.today() + timedelta(days=30)
OUT = IN + timedelta(days=3)


@pytest.fixture
async def api(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    keys._calls.clear()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    @contextlib.asynccontextmanager
    async def journal_session():
        yield db
    monkeypatch.setattr(keys, "journal_session", journal_session)

    double = ResourceTypeCatalog(company_id=company_id, name="Quarto duplo", requires_service=True,
                                 default_start_time=time(14), default_end_time=time(12))
    suite = ResourceTypeCatalog(company_id=company_id, name="Suite", requires_service=True,
                                default_start_time=time(14), default_end_time=time(12))
    db.add_all([double, suite])
    await db.flush()
    rooms = [Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=double.id,
                      name=f"Quarto 10{n}", capacity=2) for n in (1, 2)]
    db.add_all(rooms + [Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=suite.id,
                                 name="Suite 1", capacity=4)])
    rate = Service(company_id=company_id, code="DUP", name="Diária duplo", price=20000, vat_id=ctx["vat_nor"].id,
                   resource_type_id=double.id)
    suite_rate = Service(company_id=company_id, code="STE", name="Diária suite", price=50000,
                         vat_id=ctx["vat_nor"].id, resource_type_id=suite.id)
    db.add_all([rate, suite_rate])
    await db.commit()
    plain = (await keys.create_key(db, company_id, ctx["gestor"].id, "Site do hotel", ["bookings"]))["key"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        # ids read once: a refused booking rolls the shared test session back (its objects expire)
        yield {**ctx, "client": client, "h": {"X-API-Key": plain}, "rooms": rooms, "double_id": str(double.id),
               "rate_id": str(rate.id), "suite_rate_id": str(suite_rate.id)}
    app.dependency_overrides.pop(get_db, None)


def _key(api, key=None):
    return {**api["h"], "Idempotency-Key": key or str(uuid.uuid4())}


def _body(api, **extra):
    return {"resource_type_id": api["double_id"], "service_id": api["rate_id"],
            "check_in": IN.isoformat(), "check_out": OUT.isoformat(), "guest_name": "Maria Domingos",
            "party_size": 2, "guest_phone": "+244923456789", "external_reference": "WEB-77", **extra}


async def test_availability_per_type_with_the_rates_and_the_stay(api):
    found = await api["client"].get(API + "/bookings/availability", headers=api["h"],
                                    params={"check_in": IN.isoformat(), "check_out": OUT.isoformat()})
    assert found.status_code == 200, found.text
    by_type = {t["resource_type"]: t for t in found.json()}
    double = by_type["Quarto duplo"]
    assert double["available"] == 2 and double["total"] == 2 and double["nights"] == 3
    assert double["starts_at"].endswith("14:00:00+01:00") and double["ends_at"].endswith("12:00:00+01:00")
    assert double["rates"] == [{"service_id": api["rate_id"], "name": "Diária duplo", "price": 20000.0,
                                "vat_rate": 14.0, "price_with_vat": 22800.0, "stay_total_with_vat": 68400.0}]
    big = (await api["client"].get(API + "/bookings/availability", headers=api["h"], params={
        "check_in": IN.isoformat(), "check_out": OUT.isoformat(), "party_size": 3})).json()
    assert {t["resource_type"]: t["available"] for t in big} == {"Quarto duplo": 0, "Suite": 1}
    wrong = await api["client"].get(API + "/bookings/availability", headers=api["h"],
                                    params={"check_in": OUT.isoformat(), "check_out": IN.isoformat()})
    assert wrong.status_code == 422 and "check_out" in wrong.json()["detail"]


async def test_a_type_is_booked_pending_with_a_free_room_and_the_gestor_is_told(api, db):
    client = api["client"]
    db.add(NotificationRecipient(company_id=api["company"].id, name="Dono", channel="EMAIL",
                                 address="dono@hotel.ao", events=["RESERVA_ONLINE"]))
    await db.commit()
    created = await client.post(API + "/bookings", headers=_key(api), json=_body(api))
    assert created.status_code == 201, created.text
    booking = created.json()
    assert booking["status"] == "PENDENTE" and booking["external_reference"] == "WEB-77" and booking["can_cancel"]
    assert booking["resource"]["name"] == "Quarto 101" and booking["resource_type"]["name"] == "Quarto duplo"
    stored = await db.get(Booking, uuid.UUID(booking["id"]))
    assert stored.api_key_id is not None and "+244923456789" in stored.notes
    assert stored.created_by_user_id == api["gestor"].id
    told = (await db.execute(select(NotificationOutbox).where(NotificationOutbox.event == "RESERVA_ONLINE"))).scalars().all()
    assert len(told) == 1 and "Maria Domingos" in told[0].text and "WEB-77" in told[0].text

    second = (await client.post(API + "/bookings", headers=_key(api), json=_body(api, external_reference="WEB-78"))).json()
    assert second["resource"]["name"] == "Quarto 102"
    full = await client.post(API + "/bookings", headers=_key(api), json=_body(api, external_reference="WEB-79"))
    assert full.status_code == 409 and "Quarto duplo" in full.json()["detail"]
    left = (await client.get(API + "/bookings/availability", headers=api["h"], params={
        "check_in": IN.isoformat(), "check_out": OUT.isoformat(), "resource_type_id": api["double_id"]})).json()
    assert left[0]["available"] == 0


async def test_idempotent_and_read_back(api, db):
    client, key = api["client"], "WEB-77-attempt"
    first = await client.post(API + "/bookings", headers=_key(api, key), json=_body(api))
    again = await client.post(API + "/bookings", headers=_key(api, key), json=_body(api))
    assert again.json()["id"] == first.json()["id"] and again.headers["idempotent-replayed"] == "true"
    assert (await db.execute(select(func.count(Booking.id)))).scalar_one() == 1
    by_ref = (await client.get(API + "/bookings", headers=api["h"], params={"external_reference": "WEB-77"})).json()
    assert by_ref["total"] == 1 and by_ref["items"][0]["id"] == first.json()["id"]
    one = (await client.get(f"{API}/bookings/{first.json()['id']}", headers=api["h"])).json()
    assert one["guest_name"] == "Maria Domingos" and one["service"]["name"] == "Diária duplo"


async def test_cancel_only_its_own_and_before_the_check_in(api, db):
    client = api["client"]
    booking = (await client.post(API + "/bookings", headers=_key(api), json=_body(api))).json()
    cancelled = await client.post(f"{API}/bookings/{booking['id']}/cancel", headers=api["h"])
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELADA" and not cancelled.json()["can_cancel"]
    assert (await client.post(f"{API}/bookings/{booking['id']}/cancel", headers=api["h"])).status_code == 200  # again: same

    # a booking made at the desk: not the site's - not seen, not cancelled
    desk = Booking(company_id=api["company"].id, resource_id=api["rooms"][1].id, starts_at=api["rooms"][1].created_at,
                   ends_at=api["rooms"][1].created_at + timedelta(days=1), created_by_user_id=api["gestor"].id,
                   guest_name="Balcão")
    db.add(desk)
    await db.commit()
    assert (await client.get(f"{API}/bookings/{desk.id}", headers=api["h"])).status_code == 404
    assert (await client.post(f"{API}/bookings/{desk.id}/cancel", headers=api["h"])).status_code == 404
    assert (await client.get(API + "/bookings", headers=api["h"])).json()["total"] == 1

    # after the check-in: the site cannot cancel any more
    stay = (await client.post(API + "/bookings", headers=_key(api), json=_body(api, external_reference="WEB-80"))).json()
    stored = await db.get(Booking, uuid.UUID(stay["id"]))
    stored.status = BookingStatus.EM_CURSO
    await db.commit()
    refused = await client.post(f"{API}/bookings/{stay['id']}/cancel", headers=api["h"])
    assert refused.status_code == 422 and "receção" in refused.json()["detail"]


async def test_refusals(api, db):
    client, company_id = api["client"], api["company"].id
    no_rate = await client.post(API + "/bookings", headers=_key(api), json=_body(api, service_id=None))
    assert no_rate.status_code == 422  # a room always has its rate
    other_rate = await client.post(API + "/bookings", headers=_key(api), json=_body(api, service_id=api["suite_rate_id"]))
    assert other_rate.status_code == 422 and "tarifa" in other_rate.json()["detail"]
    both = await client.post(API + "/bookings", headers=_key(api), json=_body(
        api, starts_at=f"{IN.isoformat()}T10:00:00", ends_at=f"{IN.isoformat()}T11:00:00"))
    assert both.status_code == 422
    past = await client.post(API + "/bookings", headers=_key(api), json=_body(
        api, check_in=(date.today() - timedelta(days=5)).isoformat(), check_out=(date.today() - timedelta(days=3)).isoformat()))
    assert past.status_code == 422 and "passou" in past.json()["detail"]
    unknown = await client.post(API + "/bookings", headers=_key(api), json=_body(api, resource_type_id=str(uuid.uuid4())))
    assert unknown.status_code == 404
    bad_phone = await client.post(API + "/bookings", headers=_key(api), json=_body(api, guest_phone="abc"))
    assert bad_phone.status_code == 422
    catalog_only = (await keys.create_key(db, company_id, None, "Loja", ["catalog"]))["key"]
    refused = await client.get(API + "/bookings/availability", headers={"X-API-Key": catalog_only},
                               params={"check_in": IN.isoformat(), "check_out": OUT.isoformat()})
    assert refused.status_code == 403
    assert (await db.execute(select(func.count(Booking.id)))).scalar_one() == 0
