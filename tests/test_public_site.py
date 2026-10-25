"""
The public site (rmsystem.co.ao): GET /api/v1/public/site gives, without a login, the plans on sale, the sectors and the
contacts - only on the platform (PUBLIC_SITE); on a client's server the route does not exist. The SUPER_ADMIN sets the
contacts in Configurações (/admin/site-settings).
"""
import httpx
import pytest

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.user import User, UserRole
from app.services.plan_service import save_plan


@pytest.fixture
def client_for(db):
    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    yield lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.pop(get_db, None)


async def test_only_on_the_platform(db, client_for, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUBLIC_SITE", False)
    async with client_for() as client:
        assert (await client.get("/api/v1/public/site")).status_code == 404


async def test_the_site_shows_the_plans_on_sale(db, client_for, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUBLIC_SITE", True)
    await save_plan(db, None, {"name": "Popular", "price_monthly": 15000, "price_annual": 150000, "is_popular": True,
                               "limits": {"max_users": 3}, "options": ["GUIAS"], "sort_order": 2})
    await save_plan(db, None, {"name": "Primeiro", "price_monthly": 9000, "sort_order": 1})
    hidden = await save_plan(db, None, {"name": "Antigo", "price_monthly": 1000})
    hidden.is_active = False
    await db.commit()

    async with client_for() as client:
        response = await client.get("/api/v1/public/site")
    assert response.status_code == 200 and "max-age" in response.headers["cache-control"]
    site = response.json()
    assert [p["name"] for p in site["plans"]] == ["Primeiro", "Popular"]  # the order chosen, never the inactive one
    popular = site["plans"][1]
    assert popular["prices"]["MENSAL"] == 15000 and popular["prices"]["ANUAL"] == 150000
    assert popular["prices"]["VITALICIA"] is None and popular["is_popular"]
    assert popular["limits"]["max_users"] == 3 and popular["limits"]["max_pos"] is None  # None: unlimited
    assert popular["options"] == ["GUIAS"]
    codes = {s["code"]: s for s in site["sectors"]}
    assert codes["HOTEL"]["ready"] and not codes["CONTABILIDADE"]["ready"]
    assert site["contacts"] == {"whatsapp": None, "email": None} and site["agt_validation_number"] is None


async def test_the_contacts_are_set_by_the_super_admin(db, client_for, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUBLIC_SITE", True)
    admin = User(company_id=None, full_name="Admin", phone_number="+244900000001", password_hash=hash_password("x" * 8),
                 role=UserRole.SUPER_ADMIN)
    db.add(admin)
    await db.commit()
    h = {"Authorization": "Bearer " + create_access_token(subject=str(admin.id), company_id=None, role="SUPER_ADMIN")}
    async with client_for() as client:
        assert (await client.put("/api/v1/admin/site-settings", json={"site_whatsapp": "923000000"}, headers=h)).status_code == 422
        assert (await client.put("/api/v1/admin/site-settings", json={"site_email": "nao-e-email"}, headers=h)).status_code == 422
        saved = await client.put("/api/v1/admin/site-settings", headers=h,
                                 json={"site_whatsapp": "+244 923 000 000", "site_email": " geral@rmsystem.co.ao "})
        assert saved.status_code == 200 and saved.json() == {"site_whatsapp": "+244923000000",
                                                             "site_email": "geral@rmsystem.co.ao"}
        site = (await client.get("/api/v1/public/site")).json()
        assert site["contacts"] == {"whatsapp": "+244923000000", "email": "geral@rmsystem.co.ao"}
        assert (await client.get("/api/v1/admin/site-settings")).status_code == 401  # the platform's only
