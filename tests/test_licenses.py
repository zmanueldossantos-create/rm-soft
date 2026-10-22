"""
Licenças das instalações locais: RM SOFT signs a file (company NIF + server code + contract); a client's server
(LICENSE_REQUIRED) reads its plan, limits and dates from that file only. A changed file, another company's or another
server's is refused; without a valid licence: 7 days, then read only; the import stays possible in read only.
"""
import base64
from datetime import date, timedelta

import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.core import license as lic
from app.core import license_key
from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.services import license_service
from app.services.auth_service import create_user
from app.services.permission_service import seed_permission_catalog
from app.services.plan_service import PlanLimitError, entitlements, save_plan, set_contract, subscription


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


@pytest.fixture
def keys(monkeypatch):
    private = Ed25519PrivateKey.generate()
    monkeypatch.setattr(license_key, "PUBLIC_KEY", _b64(private.public_key().public_bytes_raw()))
    monkeypatch.setattr(get_settings(), "LICENSE_PRIVATE_KEY", _b64(private.private_bytes_raw()))
    monkeypatch.setattr(lic, "_machine_identity", lambda: "machine-A")
    license_service._checked.clear()
    return private


def _on(monkeypatch, machine="machine-A", required=True):
    monkeypatch.setattr(lic, "_machine_identity", lambda: machine)
    monkeypatch.setattr(get_settings(), "LICENSE_REQUIRED", required)


def test_a_signed_file_reads_back_and_a_changed_one_is_refused(keys):
    assert lic.can_sign()
    text = lic.sign_license({"nif": "5000000000", "plan": {"name": "Mini"}})
    assert lic.read_license(text)["plan"]["name"] == "Mini"
    assert lic.read_license(text[:40] + "\n  " + text[40:])["nif"] == "5000000000"  # pasted from an email
    body, sig = text[len(lic.PREFIX):].split(".")
    forged = lic.PREFIX + _b64(b'{"nif":"5000000000","plan":{"name":"Tudo"}}') + "." + sig
    with pytest.raises(lic.LicenseError, match="assinatura não corresponde"):
        lic.read_license(forged)
    with pytest.raises(lic.LicenseError, match="não é uma licença"):
        lic.read_license("olá")
    other = Ed25519PrivateKey.generate()  # signed by someone else
    payload = b'{"nif":"5000000000"}'
    with pytest.raises(lic.LicenseError):
        lic.read_license(lic.PREFIX + _b64(payload) + "." + _b64(other.sign(payload)))


def test_the_installation_code(keys):
    code = lic.installation_code()
    assert len(code) == 19 and code.count("-") == 3 and lic.normalize_code(code.replace("-", "").lower()) == code
    with pytest.raises(lic.LicenseError, match="inválido"):
        lic.normalize_code("123")


async def _licensed_company(db, ctx, monkeypatch, billing="MENSAL", start=None, limits=None, name="Mini"):
    plan = await save_plan(db, None, {"name": name, "limits": limits or {"max_users": 2}, "options": ["GUIAS"]})
    await set_contract(db, ctx["company"].id, {"plan_id": plan.id, "billing": billing, "deployment_mode": "LOCAL",
                                               "start_date": start or date.today()})
    content, name = await license_service.generate_license(db, ctx["company"].id, lic.installation_code())
    assert name.startswith("licenca_5000000000_") and name.endswith(".lic")
    return content


async def test_generate_needs_a_local_contract(db, company_with_essentials, keys):
    ctx = company_with_essentials
    with pytest.raises(lic.LicenseError, match="não tem contrato"):
        await license_service.generate_license(db, ctx["company"].id, lic.installation_code())
    plan = await save_plan(db, None, {"name": "Mini"})
    await set_contract(db, ctx["company"].id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "SAAS"})
    with pytest.raises(lic.LicenseError, match="só para a instalação local"):
        await license_service.generate_license(db, ctx["company"].id, lic.installation_code())


async def test_the_terms_come_from_the_licence_on_a_clients_server(db, company_with_essentials, keys, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    content = await _licensed_company(db, ctx, monkeypatch)
    _on(monkeypatch)

    no_licence = await subscription(db, company_id)  # created today, no licence: it still works (7 days)
    assert no_licence["license_problem"] and not no_licence["read_only"]

    _on(monkeypatch, machine="machine-B")  # copied to another server: refused
    with pytest.raises(lic.LicenseError, match="outro servidor"):
        await license_service.import_license(db, company_id, content, None)
    _on(monkeypatch)
    view = await license_service.import_license(db, company_id, content, None)
    assert view["valid"] and view["plan"] == "Mini" and view["status"] == "ATIVO"

    # the database's contract is not used any more: a bigger plan there changes nothing
    big = await save_plan(db, None, {"name": "Grande", "limits": {}})
    await set_contract(db, company_id, {"plan_id": big.id, "billing": "ANUAL", "deployment_mode": "LOCAL"})
    assert (await entitlements(db, company_id))["limits"]["max_users"] == 2
    await create_user(db, company_id, "Caixa 1", "+244923000601", "Teste@2026", "CAIXA")
    with pytest.raises(PlanLimitError, match="O plano Mini permite 2"):
        await create_user(db, company_id, "Caixa 2", "+244923000602", "Teste@2026", "CAIXA")

    # the server changed (a new machine): the stored licence no longer matches - back to "no licence"
    _on(monkeypatch, machine="machine-B")
    assert (await subscription(db, company_id))["license_problem"].startswith("Esta licença foi emitida para outro servidor")


async def test_another_companys_licence_is_refused(db, company_with_essentials, keys, monkeypatch):
    ctx = company_with_essentials
    content = await _licensed_company(db, ctx, monkeypatch)
    ctx["company"].nif = "5999999999"
    await db.commit()
    _on(monkeypatch)
    with pytest.raises(lic.LicenseError, match="NIF 5000000000"):
        await license_service.import_license(db, ctx["company"].id, content, None)


async def test_an_ended_licence_is_read_only_and_a_new_one_imports(db, company_with_essentials, keys, monkeypatch):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    old = await _licensed_company(db, ctx, monkeypatch, start=date.today() - timedelta(days=90))
    _on(monkeypatch)
    await license_service.import_license(db, company_id, old, None)
    assert (await subscription(db, company_id))["read_only"]

    _on(monkeypatch, required=False)  # the platform issues the renewal
    renewal = await _licensed_company(db, ctx, monkeypatch, name="Mini 2027")
    _on(monkeypatch)

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            gestor = {"Authorization": "Bearer " + create_access_token(
                subject=str(ctx["gestor"].id), company_id=str(company_id), role="GESTOR")}
            refused = await client.post("/api/v1/establishments", json={"code": "L1", "name": "Loja 1"}, headers=gestor)
            assert refused.status_code == 423 and "Licença" in refused.json()["detail"]
            seen = (await client.get("/api/v1/company/me/license", headers=gestor)).json()
            assert seen["required"] and seen["status"] == "BLOQUEADO" and seen["installation_code"] == lic.installation_code()
            bad = await client.post("/api/v1/company/me/license", json={"content": "lixo"}, headers=gestor)
            assert bad.status_code == 422
            done = await client.post("/api/v1/company/me/license", json={"content": renewal}, headers=gestor)
            assert done.status_code == 200, done.text
            assert done.json()["status"] == "ATIVO"
            again = await client.post("/api/v1/establishments", json={"code": "L1", "name": "Loja 1"}, headers=gestor)
            assert again.status_code in (200, 201)
    finally:
        app.dependency_overrides.pop(get_db, None)


def test_the_key_tool_writes_the_pair_once(tmp_path, monkeypatch):
    from app.tools import license_keys
    key_file = tmp_path / "license_key.py"
    key_file.write_text('PUBLIC_KEY = ""\n', encoding="utf-8")
    monkeypatch.setattr(license_keys, "KEY_FILE", key_file)
    monkeypatch.setattr(license_keys, "ROOT", tmp_path)
    (tmp_path / ".env").write_text("JWT_SECRET_KEY=x\n", encoding="utf-8")
    assert license_keys.main([]) == 0
    env = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "JWT_SECRET_KEY=x" in env and "LICENSE_PRIVATE_KEY=" in env
    assert 'PUBLIC_KEY = ""' not in key_file.read_text(encoding="utf-8")
    assert license_keys.main([]) == 1  # never twice by accident
