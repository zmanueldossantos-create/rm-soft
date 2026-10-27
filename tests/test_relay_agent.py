"""
The relay agent (P4 step 5b), on the client's server: set by the gestor (the platform's address and the relay's secret),
it sends the keys' hashes and the photo, takes the site's calls from the platform, runs them on this server's own API -
in-process, with a token that never leaves it - and sends the answers back (a PDF too).

The platform and the client's server are both this test app here: the platform's «is it one of my keys» check is
turned off so that the company's key goes through the relay (on a real platform the key is not in its database).
"""
import asyncio
import uuid

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.public_v1 import relay as site_relay
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.product import Product
from app.models.relay import RelayAgentSettings
from app.services import api_key_service as keys
from app.services import relay_agent, relay_service
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
from app.services.plan_service import save_plan, set_contract

API = "/api/public/v1"
BASE = "/api/v1/company/me/api-keys"


@pytest.fixture
async def setup(db, company_with_essentials, test_engine, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    keys._calls.clear()
    sessions = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)
    monkeypatch.setattr(relay_service, "relay_session", sessions)
    monkeypatch.setattr(relay_agent, "agent_session", sessions)
    monkeypatch.setattr(relay_service, "POLL_SECONDS", 0.05)
    monkeypatch.setattr(relay_service, "WAIT_SECONDS", 4)

    async def own_session():
        async with sessions() as session:
            yield session
    app.dependency_overrides[get_db] = own_session

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def journal_session():
        async with sessions() as session:
            yield session
    monkeypatch.setattr(keys, "journal_session", journal_session)

    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    plan = await save_plan(db, None, {"name": "Local", "options": ["INTEGRACAO_API"]})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "LOCAL"})
    db.add(Product(company_id=company_id, code="ARZ", name="Arroz 1kg", price=1000, vat_id=ctx["vat_nor"].id))
    await db.commit()
    site_key = (await keys.create_key(db, company_id, ctx["gestor"].id, "Site", ["catalog", "customers", "documents"]))["key"]
    gestor_h = {"Authorization": "Bearer " + create_access_token(
        subject=str(ctx["gestor"].id), company_id=str(company_id), role="GESTOR")}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "client": client, "site_key": site_key, "gestor_h": gestor_h, "sessions": sessions}
    app.dependency_overrides.pop(get_db, None)


def _as_platform(monkeypatch):
    """This app plays the platform too: its relay is on, and the company's key is «not one of its own»."""
    monkeypatch.setattr(get_settings(), "RELAY_SERVER", True)

    async def never(db, key_hash):
        return False
    monkeypatch.setattr(site_relay, "platform_key", never)
    monkeypatch.setattr(relay_agent, "relay_transport", httpx.ASGITransport(app=app))


async def _link(setup, monkeypatch) -> None:
    """The SUPER_ADMIN activated the relay (platform); the technician typed its secret here (client's server)."""
    async with setup["sessions"]() as session:
        secret = (await relay_service.activate(session, setup["company"].id))["secret"]
    saved = await setup["client"].put(BASE + "/relay", headers=setup["gestor_h"],
                                      json={"relay_url": "http://test", "secret": secret, "is_active": True})
    assert saved.status_code == 200, saved.text
    return secret


async def test_the_gestor_sets_and_tests_the_link(setup, monkeypatch):
    client, h = setup["client"], setup["gestor_h"]
    assert (await client.get(BASE, headers=h)).json()["relay"] == {"configured": False}
    bad = await client.put(BASE + "/relay", headers=h, json={"relay_url": "admin.rmsystem.co.ao", "secret": "rmr_x"})
    assert bad.status_code == 422 and "Endereço" in bad.json()["detail"]
    no_secret = await client.put(BASE + "/relay", headers=h, json={"relay_url": "https://admin.rmsystem.co.ao"})
    assert no_secret.status_code == 422 and "código" in no_secret.json()["detail"]

    _as_platform(monkeypatch)
    secret = await _link(setup, monkeypatch)
    view = (await client.get(BASE, headers=h)).json()["relay"]
    assert view["configured"] and view["secret_hint"] == "•••• " + secret[-4:] and secret not in str(view)
    tested = await client.post(BASE + "/relay/test", headers=h)
    assert tested.status_code == 200, tested.text
    # the platform now knows the key - by its hash only
    async with setup["sessions"]() as session:
        from app.models.relay import RelayLink
        from sqlalchemy import select
        link = (await session.execute(select(RelayLink))).scalar_one()
        assert link.keys[0]["hash"] == keys.hash_key(setup["site_key"]) and setup["site_key"] not in str(link.keys)

    # a wrong secret: the screen says so
    await client.put(BASE + "/relay", headers=h, json={"relay_url": "http://test", "secret": "rmr_" + "w" * 30})
    refused = await client.post(BASE + "/relay/test", headers=h)
    assert refused.status_code == 422 and "recusado" in refused.json()["detail"]
    assert (await client.get(BASE, headers=h)).json()["relay"]["last_error"]


async def test_the_site_through_the_relay_server_on(setup, monkeypatch):
    _as_platform(monkeypatch)
    await _link(setup, monkeypatch)
    client, site_h = setup["client"], {"X-API-Key": setup["site_key"]}
    async with relay_agent.make_client("http://test", (await _secret(setup)), relay_agent.relay_transport) as agent:
        async with setup["sessions"]() as session:
            await relay_agent.push_keys(agent, session, setup["company"].id)
            await relay_agent.push_snapshot(agent, session, setup["company"].id)

        async def serve(times):
            for _ in range(times):
                await relay_agent.cycle(agent, setup["company"].id, wait=False)
                await asyncio.sleep(0.05)

        # a read: the site gets the server's own answer (not the photo)
        products, _ = await asyncio.gather(client.get(API + "/catalog/products", headers=site_h), serve(20))
        assert products.status_code == 200 and products.headers["x-rm-relay"] == "true"
        assert "x-rm-offline" not in products.headers and products.json()["items"][0]["name"] == "Arroz 1kg"
        # a write, then its PDF: a file through the relay
        created, _ = await asyncio.gather(client.post(API + "/documents", json={
            "type": "FP", "lines": [{"product_id": products.json()["items"][0]["id"], "quantity": 2}]},
            headers={**site_h, "Idempotency-Key": "ENC-0001"}), serve(20))
        assert created.status_code == 201, created.text
        pdf, _ = await asyncio.gather(client.get(f"{API}/documents/{created.json()['id']}/pdf", headers=site_h),
                                      serve(20))
        assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
        assert pdf.content.startswith(b"%PDF")
    # the server's journal has the relayed calls, under the site's key
    journal = (await client.get(BASE + "/journal", headers=setup["gestor_h"])).json()
    assert {j["path"] for j in journal} >= {API + "/catalog/products", API + "/documents"}


async def test_server_off_then_back(setup, monkeypatch):
    _as_platform(monkeypatch)
    await _link(setup, monkeypatch)
    client, site_h = setup["client"], {"X-API-Key": setup["site_key"]}
    async with relay_agent.make_client("http://test", await _secret(setup), relay_agent.relay_transport) as agent:
        async with setup["sessions"]() as session:
            await relay_agent.push_keys(agent, session, setup["company"].id)
    async with setup["sessions"]() as session:  # the server goes off
        from app.models.relay import RelayLink
        from sqlalchemy import update
        await session.execute(update(RelayLink).values(last_seen_at=None))
        await session.commit()
    waiting = await client.post(API + "/customers", headers=site_h,
                                json={"name": "Maria Domingos", "nif": "004567890LA041"})
    assert waiting.status_code == 202
    request_id = waiting.json()["request_id"]
    # back on: the agent's next poll answers it
    async with relay_agent.make_client("http://test", await _secret(setup), relay_agent.relay_transport) as agent:
        assert await relay_agent.cycle(agent, setup["company"].id, wait=False) == 1
    state = (await client.get(f"{API}/requests/{request_id}", headers=site_h)).json()
    assert state["status"] == "FEITO" and state["response"]["status_code"] == 201
    assert state["response"]["body"]["name"] == "Maria Domingos"
    async with setup["sessions"]() as session:
        row = await session.get(RelayAgentSettings, setup["company"].id)
        assert row.requests_done == 1


async def test_the_agent_token_never_comes_from_outside(setup):
    client = setup["client"]
    forged = await client.get(API + "/catalog/products", headers={
        "X-Relay-Agent": "guess", "X-Relay-Key-Hash": keys.hash_key(setup["site_key"])})
    assert forged.status_code == 401
    # in-process with the real token: the key's rights still apply
    item = {"id": str(uuid.uuid4()), "method": "GET", "path": "/bookings/availability", "query": None, "body": None,
            "key_hash": keys.hash_key(setup["site_key"]), "idempotency_key": None}
    assert (await relay_agent.run_request(item))["status_code"] == 403


async def test_only_on_a_local_installation(setup, monkeypatch):
    """The link is the client's server's: on the platform (SaaS) it does not exist."""
    from fastapi import HTTPException
    from app.api.v1.company.api_key_routes import _local_only
    async with setup["sessions"]() as session:
        await _local_only(session, setup["gestor"])  # local: allowed
        monkeypatch.setattr(get_settings(), "DEPLOYMENT_MODE", "saas")
        with pytest.raises(HTTPException) as refused:
            await _local_only(session, setup["gestor"])
    assert refused.value.status_code == 404


async def _secret(setup) -> str:
    from app.core.secret_box import decrypt_secret
    async with setup["sessions"]() as session:
        return decrypt_secret((await session.get(RelayAgentSettings, setup["company"].id)).secret_encrypted)


async def test_the_loop_sends_the_keys_and_the_photo_at_their_pace(setup, monkeypatch):
    from datetime import timedelta
    calls = []

    def platform(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path.rsplit("/", 1)[-1])
        return httpx.Response(200, json=[] if request.url.path.endswith("/pull") else {"ok": True})
    monkeypatch.setattr(relay_agent, "relay_transport", httpx.MockTransport(platform))
    monkeypatch.setattr(relay_agent, "RECHECK_EVERY", timedelta(milliseconds=50))
    async with setup["sessions"]() as session:
        await relay_agent.save(session, setup["company"].id, "https://relay.example", "rmr_" + "k" * 30, True)
    with pytest.raises(asyncio.TimeoutError):
        await asyncio.wait_for(relay_agent.agent_loop(setup["company"].id), timeout=0.6)
    # many polls and many settings re-reads, but the keys and the photo once each (every 1 and 5 minutes)
    assert calls.count("keys") == 1 and calls.count("snapshot") == 1 and calls.count("pull") > 3
