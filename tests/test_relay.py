"""
The relay (P4 step 5a), on the platform: the site of a company installed locally calls the platform with its key; the
company's server (its agent) takes the calls and answers them. Server off: a write waits (202, request number, then the
answer and the webhook), a catalogue / availability read is answered from the last photo, any other read is 503.
"""
import asyncio
import hashlib
import hmac
import json
import uuid
from datetime import date, time, timedelta

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_settings
from app.core.database import get_db
from app.main import app
from app.models.product import Product
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services import api_key_service as keys
from app.services import relay_service as relay
from app.services.plan_service import save_plan, set_contract
from app.services.relay_snapshot import build_snapshot

API = "/api/public/v1"
AGENT = "/api/relay/v1/agent"
SITE_KEY = "rmk_" + "s" * 40  # the site's key: it exists on the client's server only - the platform has its hash
IN = date.today() + timedelta(days=20)


@pytest.fixture
async def platform(db, company_with_essentials, test_engine, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    monkeypatch.setattr(get_settings(), "RELAY_SERVER", True)
    monkeypatch.setattr(relay, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(relay, "WAIT_SECONDS", 3)
    keys._calls.clear()
    # every request and the relay's waits: their own sessions (the site waits while the agent answers)
    sessions = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(relay, "relay_session", sessions)

    async def own_session():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = own_session

    plan = await save_plan(db, None, {"name": "Local", "options": ["INTEGRACAO_API"]})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "LOCAL"})
    db.add(Product(company_id=company_id, code="ARZ", name="Arroz 1kg", price=1000, vat_id=ctx["vat_nor"].id))
    room_type = ResourceTypeCatalog(company_id=company_id, name="Quarto duplo", requires_service=True,
                                    default_start_time=time(14), default_end_time=time(12))
    db.add(room_type)
    await db.flush()
    db.add(Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=room_type.id,
                    name="Quarto 101", capacity=2))
    db.add(Service(company_id=company_id, code="DUP", name="Diária duplo", price=20000, vat_id=ctx["vat_nor"].id,
                   resource_type_id=room_type.id))
    await db.commit()
    secret = (await relay.activate(db, company_id))["secret"]
    snapshot = await build_snapshot(db, company_id)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        agent_h = {"Authorization": "Bearer " + secret}
        put = await client.put(AGENT + "/keys", headers=agent_h, json=[
            {"id": str(uuid.uuid4()), "name": "Site do hotel", "hash": keys.hash_key(SITE_KEY),
             "scopes": ["catalog", "bookings"]}])
        assert put.status_code == 200, put.text
        assert (await client.put(AGENT + "/snapshot", headers=agent_h, json=snapshot)).status_code == 200
        yield {**ctx, "client": client, "agent_h": agent_h, "site_h": {"X-API-Key": SITE_KEY},
               "type_id": str(room_type.id), "sessions": sessions}
    app.dependency_overrides.pop(get_db, None)


async def _offline(platform):
    async with platform["sessions"]() as session:
        from app.models.relay import RelayLink
        from sqlalchemy import update
        await session.execute(update(RelayLink).values(last_seen_at=None))
        await session.commit()


async def test_server_off_reads_from_the_photo(platform):
    await _offline(platform)
    client, h = platform["client"], platform["site_h"]
    products = await client.get(API + "/catalog/products", headers=h, params={"search": "arroz"})
    assert products.status_code == 200 and products.headers["x-rm-offline"] == "true"
    assert products.headers["x-rm-snapshot-at"] and products.json()["items"][0]["price_with_vat"] == 1140
    free = await client.get(API + "/bookings/availability", headers=h,
                            params={"check_in": IN.isoformat(), "check_out": (IN + timedelta(days=2)).isoformat()})
    assert free.status_code == 200, free.text
    assert free.json()[0]["available"] == 1 and free.json()[0]["rates"][0]["stay_total_with_vat"] == 45600
    wrong = await client.get(API + "/bookings/availability", headers=h, params={"check_in": IN.isoformat()})
    assert wrong.status_code == 422
    # what needs the server: 503
    assert (await client.get(API + "/bookings", headers=h)).status_code == 503
    # its rights still apply: no «customers» right on this key
    assert (await client.get(API + "/customers", headers=h)).status_code == 403


async def test_server_off_a_write_waits_then_is_answered(platform, monkeypatch):
    await _offline(platform)
    client, h = platform["client"], platform["site_h"]
    sent = []

    async def post(url, body, headers):
        sent.append((url, body, headers))
        return 200
    monkeypatch.setattr(relay, "webhook_post", post)
    monkeypatch.setattr(relay, "callback_allowed", lambda url: True)

    body = {"resource_type_id": platform["type_id"], "guest_name": "Maria", "check_in": IN.isoformat(),
            "check_out": (IN + timedelta(days=2)).isoformat()}
    no_key = await client.post(API + "/bookings", headers=h, json=body)
    assert no_key.status_code == 422 and "Idempotency-Key" in no_key.json()["detail"]
    write_h = {**h, "Idempotency-Key": "WEB-1", "X-Callback-Url": "https://site.example/rm"}
    waiting = await client.post(API + "/bookings", headers=write_h, json=body)
    assert waiting.status_code == 202 and waiting.json()["status"] == "PENDENTE"
    request_id = waiting.json()["request_id"]
    assert waiting.headers["location"] == f"{API}/requests/{request_id}"
    again = await client.post(API + "/bookings", headers=write_h, json=body)
    assert again.json()["request_id"] == request_id  # the site's retry: kept once
    other = await client.post(API + "/bookings", headers=write_h, json={**body, "guest_name": "Outro"})
    assert other.status_code == 422
    assert (await client.get(f"{API}/requests/{request_id}", headers=h)).json()["status"] == "PENDENTE"

    # the server comes back: its agent takes the request and answers it
    taken = (await client.post(AGENT + "/pull", headers=platform["agent_h"], params={"wait": False})).json()
    assert [t["id"] for t in taken] == [request_id] and taken[0]["idempotency_key"] == "WEB-1"
    assert taken[0]["body"]["guest_name"] == "Maria" and taken[0]["key_hash"] == keys.hash_key(SITE_KEY)
    answer = {"id": "b-1", "status": "PENDENTE"}
    saved = await client.post(AGENT + "/results", headers=platform["agent_h"],
                              json=[{"id": request_id, "status_code": 201, "body": answer}])
    assert saved.json() == {"saved": 1}
    state = (await client.get(f"{API}/requests/{request_id}", headers=h)).json()
    assert state["status"] == "FEITO" and state["response"] == {"status_code": 201, "body": answer}
    replay = await client.post(API + "/bookings", headers=write_h, json=body)
    assert replay.status_code == 201 and replay.json() == answer and replay.headers["idempotent-replayed"] == "true"
    # the webhook, signed with the SHA-256 of the site's own key
    for _ in range(40):
        if sent:
            break
        await asyncio.sleep(0.05)
    url, raw, headers = sent[0]
    assert url == "https://site.example/rm" and json.loads(raw)["response"]["body"] == answer
    expected = hmac.new(keys.hash_key(SITE_KEY).encode(), raw, hashlib.sha256).hexdigest()
    assert headers["X-RM-Signature"] == expected
    # nothing waits any more
    assert (await client.post(AGENT + "/pull", headers=platform["agent_h"], params={"wait": False})).json() == []


async def test_server_on_the_site_gets_the_answer_directly(platform):
    client, h, agent_h = platform["client"], platform["site_h"], platform["agent_h"]

    async def agent_once():
        for _ in range(60):
            taken = (await client.post(AGENT + "/pull", headers=agent_h, params={"wait": False})).json()
            if taken:
                await client.post(AGENT + "/results", headers=agent_h, json=[
                    {"id": taken[0]["id"], "status_code": 200, "body": {"items": ["live"], "path": taken[0]["path"],
                                                                         "query": taken[0]["query"]}}])
                return
            await asyncio.sleep(0.05)
    site, _ = await asyncio.gather(client.get(API + "/catalog/products", headers=h, params={"search": "x"}),
                                   agent_once())
    assert site.status_code == 200 and "x-rm-offline" not in site.headers
    assert site.json() == {"items": ["live"], "path": "/catalog/products", "query": "search=x"}


async def test_server_on_but_silent_a_read_falls_back_to_the_photo(platform, monkeypatch):
    monkeypatch.setattr(relay, "WAIT_SECONDS", 0.3)
    client, h = platform["client"], platform["site_h"]
    slow = await client.get(API + "/catalog/products", headers=h)
    assert slow.status_code == 200 and slow.headers["x-rm-offline"] == "true"
    # the read was dropped: the agent will not run it late
    assert (await client.post(AGENT + "/pull", headers=platform["agent_h"], params={"wait": False})).json() == []


async def test_keys_secret_and_switches(platform, db, monkeypatch):
    client = platform["client"]
    # an unknown key: the normal API answers
    assert (await client.get(API + "/catalog/products", headers={"X-API-Key": "rmk_" + "z" * 40})).status_code == 401
    # a key of a SaaS company of this platform: the API runs here (not relayed)
    plain = (await keys.create_key(db, platform["company"].id, None, "SaaS", ["catalog"]))["key"]
    direct = await client.get(API + "/catalog/products", headers={"X-API-Key": plain})
    assert direct.status_code == 200 and "x-rm-relay" not in direct.headers
    # the agent: its secret only
    assert (await client.post(AGENT + "/pull", headers={"Authorization": "Bearer rmr_wrong"})).status_code == 401
    # a new secret: the old one stops
    await relay.activate(db, platform["company"].id)
    assert (await client.post(AGENT + "/pull", headers=platform["agent_h"], params={"wait": False})).status_code == 401
    # without RELAY_SERVER: no agent routes, no relaying
    monkeypatch.setattr(get_settings(), "RELAY_SERVER", False)
    assert (await client.post(AGENT + "/pull", headers=platform["agent_h"])).status_code == 404
    assert (await client.get(API + "/catalog/products", headers=platform["site_h"])).status_code == 401


async def test_only_for_a_local_contract_and_the_callback_stays_outside(db, company_with_essentials):
    plan = await save_plan(db, None, {"name": "SaaS", "options": []})
    await set_contract(db, company_with_essentials["company"].id, {"plan_id": plan.id, "billing": "MENSAL",
                                                                    "deployment_mode": "SAAS"})
    with pytest.raises(relay.RelayError):
        await relay.activate(db, company_with_essentials["company"].id)
    for url in ("http://localhost/x", "http://127.0.0.1/x", "http://10.0.0.5/x", "http://192.168.1.10/x",
                "ftp://site.ao/x", "https:///x"):
        assert not relay.callback_allowed(url), url


async def test_the_super_admin_activates_renews_and_switches_off(db, company_with_essentials, monkeypatch):
    """Empresas → Contrato (the platform): «Ativar relé» gives the code once; a new code stops the old one."""
    from app.core.security import create_access_token, hash_password
    from app.models.user import User, UserRole
    company_id = company_with_essentials["company"].id
    admin = User(company_id=None, full_name="Admin", phone_number="+244923000777", password_hash=hash_password("x"),
                 role=UserRole.SUPER_ADMIN)
    db.add(admin)
    plan = await save_plan(db, None, {"name": "Local", "options": ["INTEGRACAO_API"]})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "LOCAL"})
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    h = {"Authorization": "Bearer " + create_access_token(subject=str(admin.id), company_id=None, role="SUPER_ADMIN")}
    url = f"/api/v1/admin/companies/{company_id}/relay"
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            assert (await client.get(url, headers=h)).status_code == 404  # not the relay server
            monkeypatch.setattr(get_settings(), "RELAY_SERVER", True)
            assert (await client.get("/api/v1/admin/license-info", headers=h)).json()["relay_server"] is True
            assert (await client.get(url, headers=h)).json() == {"link": None}
            first = (await client.post(url, headers=h)).json()
            assert first["secret"].startswith("rmr_") and first["is_active"] and not first["online"]
            assert "secret" not in (await client.get(url, headers=h)).json()["link"]
            second = (await client.post(url, headers=h)).json()
            assert second["secret"] != first["secret"]
            assert await relay.agent_link(db, first["secret"]) is None and await relay.agent_link(db, second["secret"])
            off = (await client.delete(url, headers=h)).json()["link"]
            assert off["is_active"] is False and await relay.agent_link(db, second["secret"]) is None
            # a company user is not the platform
            gestor_h = {"Authorization": "Bearer " + create_access_token(
                subject=str(company_with_essentials["gestor"].id), company_id=str(company_id), role="GESTOR")}
            assert (await client.post(url, headers=gestor_h)).status_code == 403
    finally:
        app.dependency_overrides.pop(get_db, None)
