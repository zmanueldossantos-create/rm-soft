"""
«Pedir demonstração» (public site) and «Pedidos» (SUPER_ADMIN): a request is kept with its phone in international form,
the anti-spam sets robots aside (hidden field: kept as DESCARTADO, never lost), refuses forms sent too fast and more than 5 an hour from one address;
the SUPER_ADMIN follows it (status, notes, who and when). Only on the platform (PUBLIC_SITE).
"""
import httpx
import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.demo_request import DemoRequest
from app.models.user import User, UserRole
from app.services.plan_service import save_plan

FORM = {"name": "Maria  Kiala", "company_name": "Padaria Kilamba", "phone": "923 111 222", "email": "maria@kilamba.ao",
        "sectors": ["PADARIA", "BAR", "INVENTADO"], "deployment": "LOCAL", "message": "2 caixas", "elapsed_ms": 9000}


@pytest.fixture
def client_for(db, monkeypatch):
    monkeypatch.setattr(get_settings(), "PUBLIC_SITE", True)

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    yield lambda: httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    app.dependency_overrides.pop(get_db, None)


async def _count(db) -> int:
    return (await db.execute(select(func.count(DemoRequest.id)))).scalar()


async def test_a_request_is_kept(db, client_for):
    plan = await save_plan(db, None, {"name": "Profissional", "price_monthly": 12500})
    async with client_for() as client:
        sent = await client.post("/api/v1/public/demo-requests", json={**FORM, "plan_id": str(plan.id)},
                                 headers={"X-Forwarded-For": "41.63.1.1"})
    assert sent.status_code == 201, sent.text
    request = (await db.execute(select(DemoRequest))).scalar_one()
    assert request.name == "Maria Kiala" and request.phone == "+244923111222" and request.ip == "41.63.1.1"
    assert request.sectors == ["PADARIA", "BAR"] and request.plan_id == plan.id and request.status == "NOVO"


async def test_the_anti_spam(db, client_for):
    async with client_for() as client:
        robot = await client.post("/api/v1/public/demo-requests", json={**FORM, "fax": "http://spam"})
        assert robot.status_code == 201
        kept = (await db.execute(select(DemoRequest))).scalar_one()
        assert kept.status == "DESCARTADO" and "robô" in kept.notes  # set aside, never among the new ones
        fast = await client.post("/api/v1/public/demo-requests", json={**FORM, "elapsed_ms": 800})
        assert fast.status_code == 422 and "depressa" in fast.json()["detail"]
        english = await client.post("/api/v1/public/demo-requests", json={**FORM, "phone": "12", "language": "en"})
        assert english.status_code == 422 and english.json()["detail"].startswith("Invalid phone")
        for _ in range(5):  # another address than the robot's (none)
            assert (await client.post("/api/v1/public/demo-requests", json=FORM,
                                      headers={"X-Forwarded-For": "41.63.2.2"})).status_code == 201
        sixth = await client.post("/api/v1/public/demo-requests", json=FORM, headers={"X-Forwarded-For": "41.63.2.2"})
        assert sixth.status_code == 429
        other = await client.post("/api/v1/public/demo-requests", json=FORM, headers={"X-Forwarded-For": "41.63.3.3"})
        assert other.status_code == 201


async def test_the_super_admin_follows_them(db, client_for, monkeypatch):
    admin = User(company_id=None, full_name="Técnico", phone_number="+244900000001", password_hash=hash_password("x" * 8),
                 role=UserRole.SUPER_ADMIN)
    db.add(admin)
    await db.commit()
    h = {"Authorization": "Bearer " + create_access_token(subject=str(admin.id), company_id=None, role="SUPER_ADMIN")}
    async with client_for() as client:
        await client.post("/api/v1/public/demo-requests", json=FORM)
        summary = (await client.get("/api/v1/admin/demo-requests/summary", headers=h)).json()
        assert summary["enabled"] and summary["counts"]["NOVO"] == 1
        listed = (await client.get("/api/v1/admin/demo-requests", headers=h)).json()
        assert listed[0]["company_name"] == "Padaria Kilamba" and listed[0]["deployment_label"] == "No servidor do cliente"
        assert [s["name"] for s in listed[0]["sectors"]] == ["Padaria", "Bar"]
        done = await client.patch(f"/api/v1/admin/demo-requests/{listed[0]['id']}", headers=h,
                                  json={"status": "CONTACTADO", "notes": "Demo marcada para 2.ª feira"})
        assert done.status_code == 200 and done.json()["handled_by"] == "Técnico" and done.json()["handled_at"]
        assert (await client.patch(f"/api/v1/admin/demo-requests/{listed[0]['id']}", headers=h,
                                   json={"status": "OUTRO"})).status_code == 422
        assert len((await client.get("/api/v1/admin/demo-requests?status_filter=NOVO", headers=h)).json()) == 0
        assert (await client.get("/api/v1/admin/demo-requests")).status_code == 401
        monkeypatch.setattr(get_settings(), "PUBLIC_SITE", False)  # a client's server: the form does not exist
        assert (await client.post("/api/v1/public/demo-requests", json=FORM)).status_code == 404
