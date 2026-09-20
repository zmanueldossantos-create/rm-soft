"""
Tests for the sector separation (ENFORCE_CAPABILITIES): off = nothing changes; on = a permission
whose capability the company does not get from its granted modules is refused (GESTOR included),
core permissions always work, dependencies come along, revoking a module removes its permissions
but never its grant row, and /permissions/mine and the matrix follow.
"""
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.deps import require_permission
from app.core.config import get_settings
from app.models.company_module import CompanyModule
from app.models.module import Module
from app.models.user import UserRole
from app.services.company_module_service import set_company_modules
from app.services.permission_service import (
    get_permission_matrix, has_permission, list_my_permissions, seed_default_role_permissions, seed_permission_catalog,
)
from app.services.sector_service import seed_sector_catalog


async def _module_id(db, code):
    return (await db.execute(select(Module).where(Module.code == code))).scalar_one().id


async def _setup(db, ctx, *sector_codes):
    """Seeds permissions and sectors, then grants exactly these sectors to the company."""
    company_id = ctx["company"].id
    await seed_permission_catalog(db)
    await seed_default_role_permissions(db, company_id)
    await seed_sector_catalog(db)
    ids = [await _module_id(db, code) for code in sector_codes]
    await set_company_modules(db, company_id, ids)
    return company_id


def _enforce(monkeypatch, value=True):
    monkeypatch.setattr(get_settings(), "ENFORCE_CAPABILITIES", value)


@pytest.mark.asyncio
async def test_enforcement_off_changes_nothing(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials)  # no sector granted at all
    _enforce(monkeypatch, False)
    assert await has_permission(db, company_id, "GESTOR", "stock:view") is True
    assert await has_permission(db, company_id, "ARMAZENISTA", "stock:view") is True
    assert "bookings:view" in await list_my_permissions(db, company_id, "GESTOR")
    assert "bookings:view" in {e["code"] for e in await get_permission_matrix(db, company_id)}


@pytest.mark.asyncio
async def test_enforced_company_without_modules_keeps_only_the_core(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials)
    _enforce(monkeypatch)
    for code in ("stock:view", "bookings:view", "open_accounts:view", "hotel:checkin"):
        assert await has_permission(db, company_id, "GESTOR", code) is False, code
    assert await has_permission(db, company_id, "ARMAZENISTA", "stock:view") is False  # granted to the role, but no capability
    for code in ("pos:view", "invoices:view", "customers:view"):
        assert await has_permission(db, company_id, "GESTOR", code) is True, code
    assert await has_permission(db, company_id, "CAIXA", "pos:view") is True


@pytest.mark.asyncio
async def test_enforced_capabilities_follow_the_granted_modules(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials, "PADARIA")
    _enforce(monkeypatch)
    for code in ("stock:view", "production:produce", "recipes:view"):
        assert await has_permission(db, company_id, "GESTOR", code) is True, code
    for code in ("resources:view", "bookings:view", "open_accounts:view", "hotel:checkin"):
        assert await has_permission(db, company_id, "GESTOR", code) is False, code
    assert await has_permission(db, company_id, "ARMAZENISTA", "production:view") is True


@pytest.mark.asyncio
async def test_enforced_dependencies_bring_resources_with_bookings(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials, "SPA_SALAO")
    _enforce(monkeypatch)
    for code in ("resources:view", "bookings:create"):
        assert await has_permission(db, company_id, "GESTOR", code) is True, code
    for code in ("stock:view", "open_accounts:view", "hotel:checkin"):
        assert await has_permission(db, company_id, "GESTOR", code) is False, code


@pytest.mark.asyncio
async def test_revoking_a_module_removes_its_permissions_but_not_the_grant_row(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials, "BAR")
    bar_id = await _module_id(db, "BAR")
    _enforce(monkeypatch)
    assert await has_permission(db, company_id, "GESTOR", "stock:view") is True

    await set_company_modules(db, company_id, [])
    assert await has_permission(db, company_id, "GESTOR", "stock:view") is False
    grant = (await db.execute(
        select(CompanyModule).where(CompanyModule.company_id == company_id, CompanyModule.module_id == bar_id)
    )).scalar_one()
    assert grant.is_enabled is False  # switched off, never deleted


@pytest.mark.asyncio
async def test_my_permissions_and_matrix_follow_the_active_capabilities(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials, "BAR")  # STOCK + OPEN_ACCOUNTS
    _enforce(monkeypatch)
    mine = set(await list_my_permissions(db, company_id, "GESTOR"))
    assert {"stock:view", "open_accounts:view", "pos:view"} <= mine
    assert not ({"bookings:view", "production:view", "resources:view", "hotel:checkin"} & mine)

    armazenista = set(await list_my_permissions(db, company_id, "ARMAZENISTA"))
    assert "stock:view" in armazenista and "production:view" not in armazenista

    matrix = {e["code"] for e in await get_permission_matrix(db, company_id)}
    assert "stock:view" in matrix and "bookings:view" not in matrix


@pytest.mark.asyncio
async def test_require_permission_refuses_a_gestor_without_the_capability(db, company_with_essentials, monkeypatch):
    company_id = await _setup(db, company_with_essentials)
    _enforce(monkeypatch)
    gestor = SimpleNamespace(role=UserRole.GESTOR, company_id=company_id)

    with pytest.raises(HTTPException) as exc_info:
        await require_permission("stock:view")(current_user=gestor, db=db)
    assert exc_info.value.status_code == 403
    assert await require_permission("pos:view")(current_user=gestor, db=db) is gestor  # core

    super_admin = SimpleNamespace(role=UserRole.SUPER_ADMIN, company_id=None)
    allowed = require_permission("tesouraria:reasons_view", also_allow_roles=("SUPER_ADMIN",))
    assert await allowed(current_user=super_admin, db=db) is super_admin  # platform role, untouched

    await set_company_modules(db, company_id, [await _module_id(db, "BAR")])
    assert await require_permission("stock:view")(current_user=gestor, db=db) is gestor