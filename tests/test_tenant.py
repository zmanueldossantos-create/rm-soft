"""
SaaS mode, livraison 1: one address per company. The login on a company's address only knows that company's users
(two companies with the same phone and password never get mixed up); the platform logs in on the admin address; a
session is refused on another address; a suspended company cannot log in nor refresh; the HTTPS proxy only gets a
certificate for a real address. The subdomain is proposed from the short name, unique, never a reserved word.
"""
import httpx
import pytest
import pytest_asyncio

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.fiscal_regime import FiscalRegime
from app.models.user import User, UserRole
from app.services.company_service import CompanyAlreadyExistsError, create_company, update_company
from app.services.tenant_service import TenantError, slugify, validate_subdomain

PHONE, PASSWORD = "+244923000111", "Teste@2026"


@pytest_asyncio.fixture
async def saas(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "DEPLOYMENT_MODE", "saas")

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    regime = FiscalRegime(name="Regime Geral (tenant)", allows_nor=True, allows_red=True, allows_ise=True)
    db.add(regime)
    await db.flush()
    companies = []
    for i, short in enumerate(["Farmácia Central", "Farmácia da Luz"]):
        companies.append(await create_company(
            db, name=f"{short} Lda", short_name=short, nif=f"541700000{i}", email=f"f{i}@teste.ao",
            phone_number=f"+24491100000{i}", gestor_full_name=f"Gestor {i}", gestor_phone_number=PHONE,
            gestor_password=PASSWORD, fiscal_regime_id=regime.id))
    db.add(User(company_id=None, full_name="Admin", phone_number="+244923999001", password_hash=hash_password(PASSWORD),
                role=UserRole.SUPER_ADMIN))
    await db.commit()
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    yield client, companies
    await client.aclose()
    app.dependency_overrides.pop(get_db, None)


async def _login(client, host, phone=PHONE):
    return await client.post("/api/v1/auth/login", json={"phone_number": phone, "password": PASSWORD},
                             headers={"X-Tenant-Host": host})


def test_subdomain_rules():
    assert slugify("Farmácia da Luz, Lda.") == "farmacia-da-luz-lda"
    assert validate_subdomain(" Farmacia-Luz ") == "farmacia-luz"
    for bad in ("admin", "www", "-luz", "luz_central", "farmácia", ""):
        with pytest.raises(TenantError):
            validate_subdomain(bad)


async def test_each_company_has_its_own_login(db, saas):
    client, (central, luz) = saas
    assert (central.subdomain, luz.subdomain) == ("farmacia-central", "farmacia-da-luz")

    # the same phone and password in both companies: the address decides
    for company in (central, luz):
        response = await _login(client, f"{company.subdomain}.localhost")
        assert response.status_code == 200
        me = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + response.json()["access_token"],
                                                          "X-Tenant-Host": f"{company.subdomain}.localhost"})
        assert me.status_code == 200 and me.json()["company_id"] == str(company.id)

    # a session is refused on another company's address
    token = (await _login(client, "farmacia-central.localhost")).json()["access_token"]
    other = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + token, "X-Tenant-Host": "farmacia-da-luz.localhost"})
    assert other.status_code == 401 and "outro endereço" in other.json()["detail"]

    # a session without an address (opened in local mode) is refused everywhere, the bare address included
    from app.core.security import create_access_token
    loose = create_access_token(subject=me.json()["id"], company_id=str(luz.id), role="GESTOR")
    for host in ("localhost", "farmacia-da-luz.localhost"):
        response = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer " + loose, "X-Tenant-Host": host})
        assert response.status_code == 401

    # no company at the address, an unknown one
    assert (await _login(client, "localhost")).status_code == 400
    assert (await _login(client, "nao-existe.localhost")).status_code == 404

    # the platform on its own address only
    assert (await _login(client, "admin.localhost", "+244923999001")).status_code == 200
    assert (await _login(client, "farmacia-central.localhost", "+244923999001")).status_code == 401
    assert (await _login(client, "admin.localhost")).status_code == 401  # a company's gestor is not a platform account

    # the login screen knows whose it is
    tenant = (await client.get("/api/v1/auth/tenant", headers={"X-Tenant-Host": "farmacia-da-luz.localhost"})).json()
    assert (tenant["kind"], tenant["name"]) == ("company", "Farmácia da Luz")


async def test_a_suspended_company_and_the_certificates(db, saas):
    client, (central, luz) = saas
    refresh_token = (await _login(client, "farmacia-da-luz.localhost")).json()["refresh_token"]
    luz.is_active = False
    await db.commit()

    response = await _login(client, "farmacia-da-luz.localhost")
    assert response.status_code == 403 and "suspensa" in response.json()["detail"]
    refreshed = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token},
                                  headers={"X-Tenant-Host": "farmacia-da-luz.localhost"})
    assert refreshed.status_code == 401

    async def check(domain):
        return (await client.get("/api/v1/auth/domain-check", params={"domain": domain})).status_code
    assert await check("farmacia-central.rmsystem.co.ao") == 200
    assert await check("admin.rmsystem.co.ao") == 200
    assert await check("farmacia-da-luz.rmsystem.co.ao") == 404  # suspended
    assert await check("inventado.rmsystem.co.ao") == 404
    assert await check("farmacia-central.localhost") == 404


async def test_the_subdomain_is_unique_and_can_change(db, saas):
    _, (central, luz) = saas
    fields = dict(name=luz.name, nif=luz.nif, email=luz.email, phone_number=luz.phone_number)
    with pytest.raises(CompanyAlreadyExistsError, match="já é usado"):
        await update_company(db, luz.id, subdomain="farmacia-central", **fields)
    with pytest.raises(CompanyAlreadyExistsError, match="reservado"):
        await update_company(db, luz.id, subdomain="admin", **fields)
    updated = await update_company(db, luz.id, subdomain="luz", **fields)
    assert updated.subdomain == "luz"
    unchanged = await update_company(db, luz.id, **fields)  # not sent: kept
    assert unchanged.subdomain == "luz"


async def test_the_local_login_screen(db, saas, monkeypatch):
    client, _ = saas
    monkeypatch.setattr(get_settings(), "DEPLOYMENT_MODE", "local")
    tenant = (await client.get("/api/v1/auth/tenant")).json()
    assert (tenant["kind"], tenant["name"]) == ("platform", None)  # several companies: none is named
    assert (await _login(client, "localhost")).status_code == 200  # local mode: every account, as before
