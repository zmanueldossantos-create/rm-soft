"""
API pública, step 1: the gestor's access keys (shown once, stored hashed, revocable), the rights of each key, the
limit of calls per minute, the journal of the calls, the plan's option INTEGRACAO_API and the read-only contract.
"""
import contextlib
from datetime import date

import httpx
import pytest
from fastapi import Depends, FastAPI
from sqlalchemy import select

from app.api.public_v1.deps import ApiContext, api_key
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models.api_key import ApiKey
from app.services import api_key_service as keys
from app.services.auth_service import create_user
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
from app.services.plan_service import save_plan, set_contract

BASE = "/api/v1/company/me/api-keys"


@pytest.fixture
async def api(db, company_with_essentials, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    cashier = await create_user(db, company_id, "Caixa", "+244923000611", "Teste@2026", "CAIXA")
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await db.commit()
    keys._calls.clear()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    @contextlib.asynccontextmanager
    async def journal_session():
        yield db
    monkeypatch.setattr(keys, "journal_session", journal_session)

    def headers(user):
        token = create_access_token(subject=str(user.id), company_id=str(company_id), role=user.role.value)
        return {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "client": client, "gestor_h": headers(ctx["gestor"]), "cashier_h": headers(cashier)}
    app.dependency_overrides.pop(get_db, None)


async def _new_key(api, scopes=("catalog",), name="Site do hotel") -> dict:
    created = await api["client"].post(BASE, headers=api["gestor_h"], json={"name": name, "scopes": list(scopes)})
    assert created.status_code == 201, created.text
    return created.json()


async def test_the_key_is_shown_once_and_stored_hashed(api, db):
    client = api["client"]
    listed = (await client.get(BASE, headers=api["gestor_h"])).json()
    assert listed["allowed"] and listed["keys"] == [] and {s["code"] for s in listed["scopes"]} == set(keys.SCOPES)

    created = await _new_key(api, ["catalog", "documents"])
    plain = created["key"]
    assert plain.startswith("rmk_") and len(plain) == 44 and created["prefix"] == plain[:12]
    stored = (await db.execute(select(ApiKey))).scalar_one()
    assert stored.key_hash == keys.hash_key(plain) and plain not in (stored.key_hash, stored.prefix)
    again = (await client.get(BASE, headers=api["gestor_h"])).json()["keys"]
    assert len(again) == 1 and "key" not in again[0] and again[0]["scopes"] == ["catalog", "documents"]

    no_name = await client.post(BASE, headers=api["gestor_h"], json={"name": " ", "scopes": ["catalog"]})
    assert no_name.status_code == 422 and "nome" in no_name.json()["detail"]
    no_scope = await client.post(BASE, headers=api["gestor_h"], json={"name": "X", "scopes": ["nada"]})
    assert no_scope.status_code == 422 and "permissão" in no_scope.json()["detail"]
    # only the gestor
    assert (await client.get(BASE, headers=api["cashier_h"])).status_code == 403
    assert (await client.post(BASE, headers=api["cashier_h"], json={"name": "X", "scopes": ["catalog"]})).status_code == 403


async def test_ping_with_a_good_a_wrong_and_a_revoked_key(api):
    client = api["client"]
    created = await _new_key(api)
    good = await client.get("/api/public/v1/ping", headers={"Authorization": "Bearer " + created["key"]})
    assert good.status_code == 200, good.text
    assert good.json()["nif"] == api["company"].nif and good.json()["key"] == "Site do hotel"
    assert (await client.get("/api/public/v1/ping", headers={"X-API-Key": created["key"]})).status_code == 200

    wrong = await client.get("/api/public/v1/ping", headers={"Authorization": "Bearer rmk_nao_existe"})
    assert wrong.status_code == 401 and "inválida" in wrong.json()["detail"]
    assert (await client.get("/api/public/v1/ping")).status_code == 401
    # a user's session token is not a key
    assert (await client.get("/api/public/v1/ping", headers=api["gestor_h"])).status_code == 401

    revoked = await client.delete(f"{BASE}/{created['id']}", headers=api["gestor_h"])
    assert revoked.status_code == 200 and revoked.json()["is_active"] is False
    after = await client.get("/api/public/v1/ping", headers={"Authorization": "Bearer " + created["key"]})
    assert after.status_code == 401


async def test_the_journal_writes_every_call_made_with_a_key(api):
    client = api["client"]
    created = await _new_key(api)
    await client.get("/api/public/v1/ping", headers={"X-API-Key": created["key"]})
    await client.get("/api/public/v1/ping", headers={"X-API-Key": "rmk_errada"})  # no key found: nothing to write
    journal = (await client.get(BASE + "/journal", headers=api["gestor_h"])).json()
    assert len(journal) == 1
    assert journal[0]["key_name"] == "Site do hotel" and journal[0]["path"] == "/api/public/v1/ping"
    assert journal[0]["status_code"] == 200 and journal[0]["method"] == "GET"


async def test_the_limit_per_minute(api):
    client = api["client"]
    plain = (await _new_key(api))["key"]
    for _ in range(keys.RATE_PER_MINUTE):
        assert (await client.get("/api/public/v1/ping", headers={"X-API-Key": plain})).status_code == 200
    over = await client.get("/api/public/v1/ping", headers={"X-API-Key": plain})
    assert over.status_code == 429 and over.headers["retry-after"] == "60"
    # the window slides: a minute later, calls pass again
    key_id = next(iter(keys._calls))
    assert keys.within_rate(key_id, now=keys._calls[key_id][-1] + 61)


async def test_nothing_without_the_option(api, db):
    client = api["client"]
    plain = (await _new_key(api))["key"]
    plan = await save_plan(db, None, {"name": "Sem API", "options": []})
    await set_contract(db, api["company"].id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "SAAS"})
    assert (await client.get(BASE, headers=api["gestor_h"])).json() == {"allowed": False}
    refused = await client.post(BASE, headers=api["gestor_h"], json={"name": "X", "scopes": ["catalog"]})
    assert refused.status_code == 422 and "Integração API" in refused.json()["detail"]
    ping = await client.get("/api/public/v1/ping", headers={"X-API-Key": plain})
    assert ping.status_code == 403 and "Integração API" in ping.json()["detail"]


def _guarded_app(db) -> FastAPI:
    """A small app with a write and a scoped route behind the guard (the real ones come with the next steps)."""
    small = FastAPI()

    @small.post("/w")
    async def write(ctx: ApiContext = Depends(api_key("documents"))):
        return {"ok": True}

    @small.get("/r")
    async def read(ctx: ApiContext = Depends(api_key("catalog"))):
        return {"ok": True}

    async def same_session():
        yield db
    small.dependency_overrides[get_db] = same_session
    return small


async def test_the_rights_of_each_key_and_the_read_only_contract(api, db):
    only_catalog = (await _new_key(api, ["catalog"]))["key"]
    both = (await _new_key(api, ["catalog", "documents"], name="Loja"))["key"]
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=_guarded_app(db)), base_url="http://test") as small:
        assert (await small.get("/r", headers={"X-API-Key": only_catalog})).status_code == 200
        refused = await small.post("/w", headers={"X-API-Key": only_catalog})
        assert refused.status_code == 403 and "Documentos" in refused.json()["detail"]
        assert (await small.post("/w", headers={"X-API-Key": both})).status_code == 200

        # a contract ended long ago: the key still reads, writes nothing
        plan = await save_plan(db, None, {"name": "Com API", "options": [keys.OPTION]})
        await set_contract(db, api["company"].id, {"plan_id": plan.id, "billing": "MENSAL", "start_date": date(2020, 1, 1)})
        locked = await small.post("/w", headers={"X-API-Key": both})
        assert locked.status_code == 423 and "só de leitura" in locked.json()["detail"]
        assert (await small.get("/r", headers={"X-API-Key": both})).status_code == 200


async def test_another_company_cannot_revoke_the_key(api, db):
    from app.models.company import Company
    created = await _new_key(api)
    stranger = Company(name="Outra Lda", nif="5000999778", email="outra2@empresa.ao", phone_number="+244923000998")
    db.add(stranger)
    await db.flush()
    other_gestor = await create_user(db, stranger.id, "Outro", "+244923000612", "Teste@2026", "GESTOR")
    await db.commit()
    other_h = {"Authorization": "Bearer " + create_access_token(subject=str(other_gestor.id), company_id=str(stranger.id),
                                                                  role="GESTOR")}
    assert (await api["client"].delete(f"{BASE}/{created['id']}", headers=other_h)).status_code == 404
    assert (await api["client"].get(BASE, headers=other_h)).json()["keys"] == []
