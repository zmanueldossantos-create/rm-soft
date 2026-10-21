"""
Acesso de suporte: the platform enters a company with the gestor's screens - with a reason, through a one-time code
opened on the company's own address, for an hour at most, until «Sair». The gestor sees every entry; the platform
user's own account never changes; a session ended or expired is refused, its refresh too.
"""
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.config import get_settings
from app.core.database import get_db
from app.core.security import create_access_token, hash_password
from app.main import app
from app.models.support_session import SupportSession
from app.models.user import User, UserRole
from app.services.permission_service import seed_permission_catalog
from app.services.support_service import SupportError, start_support


@pytest_asyncio.fixture
async def platform(db, company_with_essentials):
    ctx = company_with_essentials
    await seed_permission_catalog(db)
    ctx["company"].subdomain = "farma"
    admin = User(company_id=None, full_name="Suporte RM", phone_number="+244923999001",
                 password_hash=hash_password("Teste@2026"), role=UserRole.SUPER_ADMIN)
    db.add(admin)
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test")
    admin_token = create_access_token(subject=str(admin.id), company_id="None", role="SUPER_ADMIN")
    yield client, ctx, admin.id, admin_token
    await client.aclose()
    app.dependency_overrides.pop(get_db, None)


def _auth(token, host=None):
    return {"Authorization": "Bearer " + token, **({"X-Tenant-Host": host} if host else {})}


async def test_a_support_access_from_start_to_end(db, platform):
    client, ctx, admin_id, admin_token = platform
    company_id = ctx["company"].id
    url = f"/api/v1/admin/companies/{company_id}/support"

    refused = await client.post(url, json={"reason": "ajuda"}, headers=_auth(admin_token))
    assert refused.status_code == 422 and "motivo" in refused.json()["detail"]
    started = await client.post(url, json={"reason": "Gestor não consegue fechar a caixa"}, headers=_auth(admin_token))
    assert started.status_code == 200 and started.json()["subdomain"] == "farma"
    code = started.json()["code"]

    tokens = await client.post("/api/v1/auth/support/redeem", json={"code": code})
    assert tokens.status_code == 200
    access, refresh = tokens.json()["access_token"], tokens.json()["refresh_token"]
    assert (await client.post("/api/v1/auth/support/redeem", json={"code": code})).status_code == 401  # once only

    me = (await client.get("/api/v1/auth/me", headers=_auth(access))).json()
    assert (me["role"], me["company_id"], me["id"]) == ("GESTOR", str(company_id), str(admin_id))
    assert me["support"]["reason"] == "Gestor não consegue fechar a caixa"
    assert (await client.get("/api/v1/customers", headers=_auth(access))).status_code == 200  # the gestor's screens
    assert (await client.get("/api/v1/admin/companies", headers=_auth(access))).status_code == 403  # not the platform's

    # the platform user's own account never changes
    admin = (await db.execute(select(User).where(User.id == admin_id))).scalar_one()
    assert (admin.company_id, admin.role) == (None, UserRole.SUPER_ADMIN)

    # the gestor sees the entry
    gestor = create_access_token(subject=str(ctx["gestor"].id), company_id=str(company_id), role="GESTOR")
    log = (await client.get("/api/v1/company/me/support-sessions", headers=_auth(gestor))).json()
    assert (log[0]["admin_name"], log[0]["active"]) == ("Suporte RM", True)

    # «Sair»: the session and its refresh are refused at once
    assert (await client.post("/api/v1/auth/support/end", headers=_auth(access))).status_code == 204
    assert (await client.get("/api/v1/auth/me", headers=_auth(access))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})).status_code == 401
    log = (await client.get("/api/v1/company/me/support-sessions", headers=_auth(gestor))).json()
    assert log[0]["active"] is False and log[0]["ended_at"]


async def test_the_hour_and_the_address(db, platform, monkeypatch):
    client, ctx, admin_id, admin_token = platform
    company_id = ctx["company"].id
    admin = (await db.execute(select(User).where(User.id == admin_id))).scalar_one()

    # after the hour: refused, its refresh too
    code = (await start_support(db, admin, company_id, "Verificar o fecho do período"))["code"]
    tokens = (await client.post("/api/v1/auth/support/redeem", json={"code": code})).json()
    session = (await db.execute(select(SupportSession))).scalars().first()
    session.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    await db.commit()
    assert (await client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"]))).status_code == 401
    assert (await client.post("/api/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})).status_code == 401

    # SaaS: the code opens on the company's address only, and the session works there only
    monkeypatch.setattr(get_settings(), "DEPLOYMENT_MODE", "saas")
    code = (await start_support(db, admin, company_id, "Configurar as séries de 2027"))["code"]
    wrong = await client.post("/api/v1/auth/support/redeem", json={"code": code}, headers={"X-Tenant-Host": "outra.localhost"})
    assert wrong.status_code == 401
    code = (await start_support(db, admin, company_id, "Configurar as séries de 2027"))["code"]
    tokens = (await client.post("/api/v1/auth/support/redeem", json={"code": code},
                                headers={"X-Tenant-Host": "farma.localhost"})).json()
    assert (await client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"], "farma.localhost"))).status_code == 200
    assert (await client.get("/api/v1/auth/me", headers=_auth(tokens["access_token"], "outra.localhost"))).status_code == 401

    # a suspended company: no support access (reactivate it first)
    ctx["company"].is_active = False
    await db.commit()
    with pytest.raises(SupportError, match="suspensa"):
        await start_support(db, admin, company_id, "Ver porque foi suspensa")


async def test_a_document_issued_in_support_names_the_platform_user(db, platform):
    """Faturas «Criado por»: the person who issued it - the platform user when it was issued in support."""
    from app.models.product import Product, ProductType
    from app.services.invoice_service import create_invoice, list_invoices
    from app.core.request_context import current_user_id
    client, ctx, admin_id, admin_token = platform
    company_id = ctx["company"].id
    product = Product(company_id=company_id, code="SUP1", name="Artigo", vat_id=ctx["vat_nor"].id, price=100,
                      min_stock_threshold=0, product_type=ProductType.BEM, unit_of_measure_id=ctx["unit_un"].id)
    db.add(product)
    await db.commit()
    from app.services.stock_service import receive_stock
    await receive_stock(db, company_id, product.id, 5, warehouse_id=ctx["activity_warehouse"].id)
    current_user_id.set(admin_id)
    await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA_RECIBO",
                         lines_input=[{"product_id": product.id, "quantity": 1}])
    [invoice] = await list_invoices(db, company_id)
    assert invoice.created_by_name == "Suporte RM"


async def test_no_password_change_in_support(db, platform):
    client, ctx, admin_id, admin_token = platform
    admin = (await db.execute(select(User).where(User.id == admin_id))).scalar_one()
    code = (await start_support(db, admin, ctx["company"].id, "Verificar a configuração"))["code"]
    access = (await client.post("/api/v1/auth/support/redeem", json={"code": code})).json()["access_token"]
    refused = await client.post("/api/v1/auth/me/password", json={"current_password": "Teste@2026", "new_password": "Nova@2026"},
                                headers=_auth(access))
    assert refused.status_code == 403 and "suporte" in refused.json()["detail"]
