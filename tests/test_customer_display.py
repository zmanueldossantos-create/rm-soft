"""
Ecrã do cliente: each activity has its own welcome message and pictures (up to 6, PNG/JPG/WEBP, 2MB); the till reads
them, only the gestor changes them; nothing without the plan's option ECRA_CLIENTE.
"""
import httpx
import pytest

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.services import customer_display_service as display
from app.services.auth_service import create_user
from app.services.permission_service import seed_default_role_permissions, seed_permission_catalog
from app.services.plan_service import save_plan, set_contract

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 100


@pytest.fixture(autouse=True)
def _uploads_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setattr(display, "UPLOAD_ROOT", str(tmp_path))
    return tmp_path


@pytest.fixture
async def api(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    cashier = await create_user(db, company_id, "Caixa", "+244923000411", "Teste@2026", "CAIXA")
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await db.commit()

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session

    def headers(user):
        token = create_access_token(subject=str(user.id), company_id=str(company_id), role=user.role.value)
        return {"Authorization": "Bearer " + token}
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield {**ctx, "client": client, "gestor_h": headers(ctx["gestor"]), "cashier_h": headers(cashier)}
    app.dependency_overrides.pop(get_db, None)


async def test_defaults_then_the_gestor_sets_the_screen(api):
    client, activity_id = api["client"], api["activity"].id
    shown = (await client.get(f"/api/v1/customer-display/{activity_id}", headers=api["cashier_h"])).json()
    assert shown["allowed"] and shown["welcome_message"] is None and shown["slide_seconds"] == 8 and shown["images"] == []
    assert shown["activity_name"] == api["activity"].name

    saved = await client.put(f"/api/v1/customer-display/{activity_id}", headers=api["gestor_h"],
                             json={"welcome_message": "  Bem-vindo à Padaria!  ", "slide_seconds": 5})
    assert saved.status_code == 200, saved.text
    assert saved.json()["welcome_message"] == "Bem-vindo à Padaria!" and saved.json()["slide_seconds"] == 5
    too_fast = await client.put(f"/api/v1/customer-display/{activity_id}", headers=api["gestor_h"],
                                json={"welcome_message": "x", "slide_seconds": 1})
    assert too_fast.status_code == 422 and "entre 3 e 60" in too_fast.json()["detail"]
    # the cashier reads, never changes
    refused = await client.put(f"/api/v1/customer-display/{activity_id}", headers=api["cashier_h"],
                               json={"welcome_message": "Hack", "slide_seconds": 5})
    assert refused.status_code == 403


async def test_pictures(api, db, _uploads_in_tmp):
    client, activity_id = api["client"], api["activity"].id
    url = f"/api/v1/customer-display/{activity_id}/images"
    bad = await client.post(url, headers=api["gestor_h"], files={"file": ("promo.gif", b"GIF89a", "image/gif")})
    assert bad.status_code == 422 and "PNG, JPG ou WEBP" in bad.json()["detail"]
    big = await client.post(url, headers=api["gestor_h"],
                            files={"file": ("big.png", PNG + b"0" * display.MAX_IMAGE_BYTES, "image/png")})
    assert big.status_code == 422 and "2MB" in big.json()["detail"]
    for n in range(display.MAX_IMAGES):
        added = await client.post(url, headers=api["gestor_h"], files={"file": (f"Promoção {n}.PNG", PNG, "image/png")})
        assert added.status_code == 201, added.text
    images = added.json()["images"]
    assert len(images) == display.MAX_IMAGES
    first = images[0]["url"]
    assert first.startswith(f"/uploads/ecra/{api['company'].id}/") and first.endswith(".png")  # never the sender's name
    assert (_uploads_in_tmp / first.removeprefix("/uploads/")).read_bytes() == PNG
    seventh = await client.post(url, headers=api["gestor_h"], files={"file": ("x.png", PNG, "image/png")})
    assert seventh.status_code == 422 and "No máximo 6" in seventh.json()["detail"]

    removed = await client.delete(f"/api/v1/customer-display/images/{images[0]['id']}", headers=api["gestor_h"])
    assert removed.status_code == 200 and len(removed.json()["images"]) == display.MAX_IMAGES - 1
    assert not (_uploads_in_tmp / first.removeprefix("/uploads/")).exists()
    cashier_delete = await client.delete(f"/api/v1/customer-display/images/{images[1]['id']}", headers=api["cashier_h"])
    assert cashier_delete.status_code == 403


async def test_each_activity_has_its_own_screen(api, db):
    client, company_id = api["client"], api["company"].id
    first = api["activity"].id
    await client.put(f"/api/v1/customer-display/{first}", headers=api["gestor_h"],
                     json={"welcome_message": "Pão quente!", "slide_seconds": 8})
    # a second activity of the same company: its own (empty) screen
    from app.models.activity import Activity
    other = Activity(company_id=company_id, module_id=api["activity"].module_id, name="Bar Central")
    db.add(other)
    await db.commit()
    shown = (await client.get(f"/api/v1/customer-display/{other.id}", headers=api["cashier_h"])).json()
    assert shown["welcome_message"] is None and shown["activity_name"] == "Bar Central"
    assert (await client.get(f"/api/v1/customer-display/{first}", headers=api["cashier_h"])).json()["welcome_message"] \
        == "Pão quente!"


async def test_another_company_activity_is_not_found(api, db):
    from app.models.activity import Activity
    from app.models.company import Company
    stranger = Company(name="Outra Lda", nif="5000999777", email="outra@empresa.ao",
                       phone_number="+244923000999")
    db.add(stranger)
    await db.flush()
    theirs = Activity(company_id=stranger.id, module_id=api["activity"].module_id, name="Deles")
    db.add(theirs)
    await db.commit()
    seen = await api["client"].get(f"/api/v1/customer-display/{theirs.id}", headers=api["gestor_h"])
    assert seen.status_code == 404


async def test_nothing_without_the_option(api, db):
    company_id = api["company"].id
    plan = await save_plan(db, None, {"name": "Sem ecrã", "options": []})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "SAAS"})
    client, activity_id = api["client"], api["activity"].id
    assert (await client.get(f"/api/v1/customer-display/{activity_id}", headers=api["cashier_h"])).json() == {"allowed": False}
    refused = await client.put(f"/api/v1/customer-display/{activity_id}", headers=api["gestor_h"],
                               json={"welcome_message": "x", "slide_seconds": 5})
    assert refused.status_code == 422 and "Ecrã do cliente" in refused.json()["detail"]
