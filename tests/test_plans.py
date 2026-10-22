"""
Planos: a plan limits (users, modules, shops, tills, warehouses) and switches options on (suppliers, guias, the
assistant...); each company has one current contract - a new one keeps the previous as history. Without a contract
nothing is limited. The refusals are clear (PT) and the options the plan lacks are refused AND hidden.
"""
from datetime import date

import httpx
import pytest
from sqlalchemy import select

from app.core.database import get_db
from app.core.plan_features import OPTIONS, option_of_permission
from app.core.security import create_access_token
from app.main import app
from app.models.plan import CompanyContract
from app.services.auth_service import create_user, toggle_user_status
from app.services.company_backup_jobs import BackupSettingsError, save_backup_settings
from app.services.company_module_service import set_company_modules
from app.services.establishment_service import create_establishment
from app.services.permission_service import has_permission, list_my_permissions, seed_permission_catalog
from app.services.plan_service import (PlanError, PlanLimitError, add_months, default_end, entitlements, save_plan,
                                       set_contract, usage)
from app.services.stock_service import create_warehouse

PLAN = {"name": "Mini", "limits": {"max_users": 2, "max_modules": 1, "max_establishments": 1, "max_pos": 1,
                                   "max_warehouses": 1}, "options": ["GUIAS"]}


def test_every_option_permission_is_a_real_one():
    from app.services.permission_service import PERMISSION_CATALOG
    codes = {entry[0] for entry in PERMISSION_CATALOG}
    prefixes = {c.split(":")[0] for c in codes}
    for option in OPTIONS.values():
        for perm in option.permissions:
            assert (perm[:-2] in prefixes) if perm.endswith(":*") else (perm in codes), perm
    assert option_of_permission("suppliers:manage") == "FORNECEDORES_COMPRAS"
    assert option_of_permission("vat:return") == "APURAMENTO_IVA" and option_of_permission("vat:view") is None
    assert option_of_permission("invoices:issue") is None  # the law: never an option


def test_periods_end_the_day_before():
    assert default_end("MENSAL", date(2026, 1, 31)) == date(2026, 2, 27)
    assert default_end("ANUAL", date(2026, 11, 1)) == date(2027, 10, 31)
    assert default_end("TESTE", date(2026, 11, 1)) == date(2026, 11, 15)
    assert default_end("VITALICIA", date(2026, 11, 1)) is None
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


async def test_without_a_contract_nothing_is_limited(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    assert await entitlements(db, company_id) is None
    for i in range(3):
        await create_user(db, company_id, f"U{i}", f"+24492300010{i}", "Teste@2026", "CAIXA")


async def test_the_limits_refuse_with_a_clear_message(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    plan = await save_plan(db, None, PLAN)
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "deployment_mode": "SAAS"})
    assert (await usage(db, company_id)) == {"max_users": 1, "max_modules": 1, "max_establishments": 0, "max_pos": 1,
                                             "max_warehouses": 1}  # the activity's own warehouse does not count

    second = await create_user(db, company_id, "Caixa 1", "+244923000201", "Teste@2026", "CAIXA")
    with pytest.raises(PlanLimitError, match="O plano Mini permite 2 utilizadores ativos"):
        await create_user(db, company_id, "Caixa 2", "+244923000202", "Teste@2026", "CAIXA")
    await toggle_user_status(db, company_id, second.id, ctx["gestor"].id)  # off: room again
    with pytest.raises(PlanLimitError):  # ...but not to switch it back on and add another
        await create_user(db, company_id, "Caixa 2", "+244923000202", "Teste@2026", "CAIXA")
        await toggle_user_status(db, company_id, second.id, ctx["gestor"].id)

    await create_establishment(db, company_id, "L1", "Loja 1")
    with pytest.raises(PlanLimitError, match="1 estabelecimento ativo"):
        await create_establishment(db, company_id, "L2", "Loja 2")
    with pytest.raises(PlanLimitError, match="armazém"):
        await create_warehouse(db, company_id, "Segundo")

    from app.models.module import Module
    other = Module(name="Outro módulo")
    db.add(other)
    await db.commit()
    with pytest.raises(PlanLimitError, match="1 módulo"):
        await set_company_modules(db, company_id, [ctx["activity"].module_id, other.id])
    await set_company_modules(db, company_id, [other.id])  # a swap is fine

    from app.services.point_of_sale_service import create_point_of_sale
    with pytest.raises(PlanLimitError, match="1 caixa ativa"):
        await create_point_of_sale(db, company_id, ctx["activity"].id, "Caixa 2")


async def test_add_ons_and_a_new_contract_keep_the_history(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    plan = await save_plan(db, None, PLAN)
    first = await set_contract(db, company_id, {"plan_id": plan.id, "billing": "ANUAL", "deployment_mode": "LOCAL"})
    await create_user(db, company_id, "Caixa 1", "+244923000301", "Teste@2026", "CAIXA")
    with pytest.raises(PlanError, match="mais do que este plano permite"):  # 2 users for a plan of 1
        await set_contract(db, company_id, {"plan_id": (await save_plan(db, None, {**PLAN, "name": "Nano",
                                                        "limits": {"max_users": 1}})).id, "billing": "ANUAL"})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "ANUAL", "deployment_mode": "LOCAL",
                                        "addons": {"max_users": 3}})
    assert (await entitlements(db, company_id))["limits"]["max_users"] == 5
    for i in range(3):
        await create_user(db, company_id, f"Extra {i}", f"+24492300031{i}", "Teste@2026", "CAIXA")
    rows = (await db.execute(select(CompanyContract).where(CompanyContract.company_id == company_id))).scalars().all()
    assert len(rows) == 2 and [r.is_current for r in rows if r.id == first.id] == [False]

    with pytest.raises(PlanError, match="só para a instalação local"):
        await set_contract(db, company_id, {"plan_id": plan.id, "billing": "VITALICIA", "deployment_mode": "SAAS"})
    lifetime = await set_contract(db, company_id, {"plan_id": plan.id, "billing": "VITALICIA", "deployment_mode": "LOCAL",
                                                   "start_date": date(2026, 11, 1), "addons": {"max_users": 3}})
    assert lifetime.end_date is None and lifetime.maintenance_until == date(2027, 10, 31)


async def test_the_options_are_refused_and_hidden(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    assert await has_permission(db, company_id, "GESTOR", "suppliers:manage")
    plan = await save_plan(db, None, PLAN)  # GUIAS only
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL"})
    assert not await has_permission(db, company_id, "GESTOR", "suppliers:manage")
    assert not await has_permission(db, company_id, "GESTOR", "assistant:use")
    assert await has_permission(db, company_id, "GESTOR", "guias:manage")
    assert await has_permission(db, company_id, "GESTOR", "invoices:issue")
    mine = await list_my_permissions(db, company_id, "GESTOR")
    assert "guias:view" in mine and "suppliers:view" not in mine and "vat:return" not in mine and "vat:view" in mine

    with pytest.raises(BackupSettingsError, match="não estão incluídas no seu plano"):
        await save_backup_settings(db, company_id, "AUTOMATICA", ["23:00"])

    from app.services.ai_settings_service import AiSettingsError, update_company_ai_switches
    with pytest.raises(AiSettingsError, match="não inclui o assistente IA"):
        await update_company_ai_switches(db, company_id, True, False, False, False, None)

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            gestor = {"Authorization": "Bearer " + create_access_token(
                subject=str(ctx["gestor"].id), company_id=str(company_id), role="GESTOR")}
            refused = await client.post("/api/v1/establishments", json={"code": "L1", "name": "Loja 1"}, headers=gestor)
            assert refused.status_code in (200, 201)
            refused = await client.post("/api/v1/establishments", json={"code": "L2", "name": "Loja 2"}, headers=gestor)
            assert refused.status_code == 422 and "O plano Mini permite 1 estabelecimento" in refused.json()["detail"]
    finally:
        app.dependency_overrides.pop(get_db, None)


async def test_a_lower_plan_switches_off_what_it_does_not_include(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    full = await save_plan(db, None, {**PLAN, "name": "Tudo", "options": list(OPTIONS)})
    await set_contract(db, company_id, {"plan_id": full.id, "billing": "ANUAL"})
    row = await save_backup_settings(db, company_id, "AUTOMATICA", ["23:00"])
    assert row.mode == "AUTOMATICA"
    await set_contract(db, company_id, {"plan_id": (await save_plan(db, None, PLAN)).id, "billing": "ANUAL"})
    await db.refresh(row)
    assert row.mode == "MANUAL" and row.next_run_at is None


async def test_the_platform_screens(db, company_with_essentials):
    from app.models.user import User, UserRole
    from app.core.security import hash_password
    admin = User(company_id=None, full_name="Admin", phone_number="+244900000001", password_hash=hash_password("x" * 8),
                 role=UserRole.SUPER_ADMIN)
    db.add(admin)
    await db.commit()
    company_id = company_with_essentials["company"].id

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            h = {"Authorization": "Bearer " + create_access_token(subject=str(admin.id), company_id=None, role="SUPER_ADMIN")}
            catalog = (await client.get("/api/v1/admin/plan-catalog", headers=h)).json()
            assert [lim["code"] for lim in catalog["limits"]][0] == "max_users" and catalog["trial_days"] == 15
            made = await client.post("/api/v1/admin/plans", json={**PLAN, "price_annual": 65000}, headers=h)
            assert made.status_code == 201, made.text
            plan_id = made.json()["id"]
            twice = await client.post("/api/v1/admin/plans", json={**PLAN, "name": "mini"}, headers=h)
            assert twice.status_code == 422 and "Já existe" in twice.json()["detail"]
            bad = await client.post("/api/v1/admin/plans", json={**PLAN, "name": "X", "options": ["VOAR"]}, headers=h)
            assert bad.status_code == 422

            view = (await client.get(f"/api/v1/admin/companies/{company_id}/contract", headers=h)).json()
            assert view["current"] is None and view["limits"] is None and view["usage"]["max_users"] == 1
            saved = await client.post(f"/api/v1/admin/companies/{company_id}/contract", headers=h, json={
                "plan_id": plan_id, "billing": "ANUAL", "deployment_mode": "SAAS", "start_date": "2026-11-01"})
            assert saved.status_code == 200, saved.text
            body = saved.json()
            assert body["current"]["plan_name"] == "Mini" and body["current"]["end_date"] == "2027-10-31"
            assert body["limits"]["max_users"] == 2
            no_end = (await client.post(f"/api/v1/admin/companies/{company_id}/contract", headers=h, json={
                "plan_id": plan_id, "billing": "ANUAL", "no_end": True})).json()
            assert no_end["current"]["end_date"] is None and len(no_end["history"]) == 2
            listed = [c for c in (await client.get("/api/v1/admin/companies", headers=h)).json() if c["id"] == str(company_id)][0]
            assert listed["plan_name"] == "Mini" and listed["contract_status"] == "ATIVO" and listed["contract_end_date"] is None
            plans = (await client.get("/api/v1/admin/plans", headers=h)).json()
            assert [p["companies"] for p in plans if p["id"] == plan_id] == [1]
    finally:
        app.dependency_overrides.pop(get_db, None)


# ---------------------------------------------------------------------------------------------------- P2: the end

def _contract(billing="MENSAL", end=None, maintenance=None):
    from types import SimpleNamespace
    return SimpleNamespace(plan=SimpleNamespace(name="Mini"), billing=billing, end_date=end, maintenance_until=maintenance)


def test_the_status_along_the_contract():
    from app.services.plan_service import contract_status
    end = date(2026, 11, 30)
    assert contract_status(None)["status"] == "ATIVO"
    assert contract_status(_contract(end=end), date(2026, 11, 15))["status"] == "ATIVO"  # 15 days left
    soon = contract_status(_contract(end=end), date(2026, 11, 16))
    assert soon["status"] == "A_EXPIRAR" and soon["days_left"] == 14 and not soon["read_only"]
    assert contract_status(_contract(end=end), end)["days_left"] == 0
    grace = contract_status(_contract(end=end), date(2026, 12, 1))
    assert grace["status"] == "TOLERANCIA" and grace["days_left"] == 6 and grace["grace_until"] == date(2026, 12, 7)
    assert contract_status(_contract(end=end), date(2026, 12, 7))["status"] == "TOLERANCIA"
    over = contract_status(_contract(end=end), date(2026, 12, 8))
    assert over["status"] == "BLOQUEADO" and over["read_only"]
    assert contract_status(_contract(end=None), date(2030, 1, 1))["status"] == "ATIVO"  # sem data de fim
    life = contract_status(_contract("VITALICIA", maintenance=date(2027, 10, 31)), date(2028, 1, 1))
    assert life["status"] == "ATIVO" and not life["read_only"] and life["maintenance_over"]


async def test_a_company_ended_long_ago_is_read_only(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    plan = await save_plan(db, None, {**PLAN, "limits": {}})
    await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL", "start_date": date(2020, 1, 1)})

    async def same_session():
        yield db
    app.dependency_overrides[get_db] = same_session
    try:
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            gestor = {"Authorization": "Bearer " + create_access_token(
                subject=str(ctx["gestor"].id), company_id=str(company_id), role="GESTOR")}
            sub = (await client.get("/api/v1/company/me/subscription", headers=gestor)).json()
            assert sub["status"] == "BLOQUEADO" and sub["read_only"] and sub["plan"] == "Mini"
            refused = await client.post("/api/v1/establishments", json={"code": "L1", "name": "Loja 1"}, headers=gestor)
            assert refused.status_code == 423 and "só de leitura" in refused.json()["detail"]
            assert (await client.get("/api/v1/establishments", headers=gestor)).status_code == 200  # reading stays
            assert (await client.get("/api/v1/saf-t/export", headers=gestor)).status_code != 423
            copy = await client.post("/api/v1/company/me/backups", headers=gestor)  # a copy now stays possible
            assert copy.status_code != 423

            # a renewal opens it again at once
            await set_contract(db, company_id, {"plan_id": plan.id, "billing": "MENSAL"})
            again = await client.post("/api/v1/establishments", json={"code": "L1", "name": "Loja 1"}, headers=gestor)
            assert again.status_code in (200, 201)
    finally:
        app.dependency_overrides.pop(get_db, None)
