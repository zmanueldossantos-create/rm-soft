"""
Tests for the dynamic permission foundations: default grants, GESTOR always
allowed, removals surviving re-seeds, new catalog codes distributed once,
seeding at company creation, and two static safety nets over the route code
(every /api/v1 route is protected; every require_permission code exists).
"""
import re
from pathlib import Path

import pytest
from sqlalchemy import select

from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user import UserRole
from app.services import permission_service
from app.services.company_service import create_company
from app.services.permission_service import (
    PERMISSION_CATALOG, ProtectedRoleError, seed_permission_catalog, seed_default_role_permissions,
    has_permission, set_role_permission, get_permission_matrix, list_my_permissions,
)

RECORD = "internal_consumption:record"


async def _permission_id(db, code):
    return (await db.execute(select(Permission.id).where(Permission.code == code))).scalar_one()


async def _seed(db, company_id):
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)


@pytest.mark.asyncio
async def test_defaults_reproduce_previous_role_behaviour(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _seed(db, company_id)
    assert await has_permission(db, company_id, "ARMAZENISTA", RECORD) is True
    assert await has_permission(db, company_id, "CAIXA", RECORD) is False
    assert await has_permission(db, company_id, "CONTABILISTA", RECORD) is False


@pytest.mark.asyncio
async def test_gestor_always_allowed_and_never_stored(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _seed(db, company_id)
    assert await has_permission(db, company_id, "GESTOR", RECORD) is True
    stored = (await db.execute(select(RolePermission).where(RolePermission.role == UserRole.GESTOR))).scalars().all()
    assert stored == []
    mine = await list_my_permissions(db, company_id, "GESTOR")
    assert set(mine) == {entry[0] for entry in PERMISSION_CATALOG}
    matrix = await get_permission_matrix(db, company_id)
    assert all("GESTOR" in entry["granted_roles"] for entry in matrix)


@pytest.mark.asyncio
async def test_gestor_column_cannot_be_edited(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _seed(db, company_id)
    permission_id = await _permission_id(db, RECORD)
    with pytest.raises(ProtectedRoleError):
        await set_role_permission(db, company_id, "GESTOR", permission_id, False)
    with pytest.raises(ProtectedRoleError):
        await set_role_permission(db, company_id, "SUPER_ADMIN", permission_id, True)


@pytest.mark.asyncio
async def test_removed_grant_survives_reseed(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _seed(db, company_id)
    permission_id = await _permission_id(db, RECORD)
    await set_role_permission(db, company_id, "ARMAZENISTA", permission_id, False)
    assert await has_permission(db, company_id, "ARMAZENISTA", RECORD) is False

    await _seed(db, company_id)  # what happens at every app boot
    assert await has_permission(db, company_id, "ARMAZENISTA", RECORD) is False


@pytest.mark.asyncio
async def test_new_catalog_code_is_distributed_once(db, company_with_essentials, monkeypatch):
    company_id = company_with_essentials["company"].id
    await _seed(db, company_id)

    new_code = "test_module:action"
    monkeypatch.setattr(permission_service, "PERMISSION_CATALOG",
                        PERMISSION_CATALOG + [(new_code, "Acao de teste", "Teste", ["CAIXA"])])
    await _seed(db, company_id)
    assert await has_permission(db, company_id, "CAIXA", new_code) is True

    await set_role_permission(db, company_id, "CAIXA", await _permission_id(db, new_code), False)
    await _seed(db, company_id)
    assert await has_permission(db, company_id, "CAIXA", new_code) is False


@pytest.mark.asyncio
async def test_create_company_seeds_default_permissions(db):
    """A company created while the server is running must not be locked out
    until the next restart."""
    company = await create_company(
        db,
        name="Empresa Permissoes Lda",
        nif="5000123456",
        email="permissoes@teste.co.ao",
        phone_number="+244923000001",
        gestor_full_name="Gestor Novo",
        gestor_phone_number="+244923000002",
        gestor_password="Teste@2026",
    )
    assert await has_permission(db, company.id, "ARMAZENISTA", RECORD) is True
    assert await has_permission(db, company.id, "CAIXA", RECORD) is False


def test_every_require_permission_code_exists_in_catalog():
    """GESTOR bypasses the check, so a typo in a route's code would silently
    lock every other role out without any error - catch it statically."""
    routes_dir = Path(__file__).resolve().parent.parent / "app" / "api" / "v1"
    catalog_codes = {entry[0] for entry in PERMISSION_CATALOG}
    used: dict[str, str] = {}
    for path in routes_dir.rglob("*.py"):
        for code in re.findall(r'require_permission\(\s*"([^"]+)"', path.read_text(encoding="utf-8")):
            used[code] = path.name
    unknown = {code: file for code, file in used.items() if code not in catalog_codes}
    assert not unknown, f"require_permission codes missing from PERMISSION_CATALOG: {unknown}"


def test_every_api_route_is_protected():
    from fastapi.routing import APIRoute
    from app.main import app

    guards = {"role_checker", "permission_checker", "get_current_user"}
    public = {"/api/v1/auth/login", "/api/v1/auth/refresh"}

    def dependency_names(dependant) -> set[str]:
        names: set[str] = set()
        for dep in dependant.dependencies:
            if dep.call is not None:
                names.add(getattr(dep.call, "__name__", ""))
            names |= dependency_names(dep)
        return names

    unprotected = [
        f"{sorted(route.methods)} {route.path}"
        for route in app.routes
        if isinstance(route, APIRoute) and route.path.startswith("/api/v1")
        and route.path not in public and not (dependency_names(route.dependant) & guards)
    ]
    assert not unprotected, f"Routes without authentication/authorization: {unprotected}"

@pytest.mark.asyncio
async def test_delete_company_removes_permission_rows(db):
    """delete_company must clear the company's role_permissions and
    company_permission_seeds rows (foreign keys without cascade). Uses a bare
    company (no default warehouse, modules...) so it isolates exactly this
    cleanup - delete_company's other gaps are tracked separately."""
    from app.models.company import Company
    from app.models.company_permission_seed import CompanyPermissionSeed
    from app.services.company_service import delete_company

    company = Company(name="Empresa Para Apagar Lda", nif="5000123457", email="apagar@teste.co.ao", phone_number="+244923000011")
    db.add(company)
    await db.flush()
    company_id = company.id
    await _seed(db, company_id)

    grants = (await db.execute(select(RolePermission).where(RolePermission.company_id == company_id))).scalars().all()
    seeds = (await db.execute(select(CompanyPermissionSeed).where(CompanyPermissionSeed.company_id == company_id))).scalars().all()
    assert grants and seeds

    await delete_company(db, company_id)

    grants = (await db.execute(select(RolePermission).where(RolePermission.company_id == company_id))).scalars().all()
    seeds = (await db.execute(select(CompanyPermissionSeed).where(CompanyPermissionSeed.company_id == company_id))).scalars().all()
    assert grants == [] and seeds == []


def test_catalog_is_well_formed():
    """Unique codes in module:action form; defaults only name editable roles
    (GESTOR is implicit, SUPER_ADMIN has no company-level grants)."""
    codes = [entry[0] for entry in PERMISSION_CATALOG]
    assert len(codes) == len(set(codes)), "duplicate permission codes"
    for code, label, category, defaults in PERMISSION_CATALOG:
        assert re.fullmatch(r"[a-z_]+:[a-z_]+", code), code
        assert label and category, code
        assert set(defaults) <= set(permission_service.EDITABLE_ROLES), (code, defaults)

def test_every_catalog_permission_is_enforced_by_a_route():
    """A catalog entry that no route checks would show a checkbox in the admin
    matrix that changes nothing - catch it statically."""
    routes_dir = Path(__file__).resolve().parent.parent / "app" / "api" / "v1"
    used: set[str] = set()
    for path in routes_dir.rglob("*.py"):
        used |= set(re.findall(r'require_permission\(\s*"([^"]+)"', path.read_text(encoding="utf-8")))
    unused = {entry[0] for entry in PERMISSION_CATALOG} - used
    assert not unused, f"catalog permissions no route enforces: {sorted(unused)}"



@pytest.mark.asyncio
async def test_require_permission_also_allow_roles_skips_company_lookup(db):
    """A platform-level role listed in also_allow_roles (SUPER_ADMIN, no company,
    no grants) passes; without the option the same user is refused."""
    from types import SimpleNamespace
    from fastapi import HTTPException
    from app.api.deps import require_permission

    super_admin = SimpleNamespace(role=UserRole.SUPER_ADMIN, company_id=None)

    allowed = require_permission("tesouraria:reasons_view", also_allow_roles=("SUPER_ADMIN",))
    assert await allowed(current_user=super_admin, db=db) is super_admin

    strict = require_permission("tesouraria:reasons_view")
    with pytest.raises(HTTPException) as exc_info:
        await strict(current_user=super_admin, db=db)
    assert exc_info.value.status_code == 403
