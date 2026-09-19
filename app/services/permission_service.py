"""
Service layer for the dynamic permission system (Permission + RolePermission).

Rules:
- PERMISSION_CATALOG is the single source of truth for which permissions
  exist and which roles get them BY DEFAULT (reproducing the old hardcoded
  require_role(...) tuples, so migrating a route changes nothing at first).
- GESTOR is the company's owner role: always allowed, never stored in
  role_permissions, and its column is locked in the admin matrix (a GESTOR
  can never lock themselves out; there is no company-level rescue account).
- Defaults are distributed ONCE per (company, permission) - tracked in
  CompanyPermissionSeed - so a grant removed in the matrix survives restarts,
  while a permission added to the catalog later is distributed once to all
  companies at the next boot.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_permission_seed import CompanyPermissionSeed
from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user import UserRole

ALWAYS_ALLOWED_ROLE = "GESTOR"
EDITABLE_ROLES = ("CAIXA", "ARMAZENISTA", "CONTABILISTA")

# (code, label, category, default_roles) - GESTOR is implicit, never listed.
PERMISSION_CATALOG: list[tuple[str, str, str, list[str]]] = [
    ("consumption_reasons:view", "Ver motivos de consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
    ("consumption_reasons:manage", "Criar/editar motivos de consumo interno", "Consumo Interno", []),
    ("internal_consumption:view", "Ver historico de consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
    ("internal_consumption:record", "Registar consumo interno", "Consumo Interno", ["ARMAZENISTA"]),
]


class ProtectedRoleError(Exception):
    """Raised when someone tries to edit the grants of a role that is not editable."""


async def _ensure_catalog(db: AsyncSession) -> dict[str, Permission]:
    """Inserts (flush only, no commit) any catalog entry missing from the
    platform-wide Permission table and returns every permission by code."""
    result = await db.execute(select(Permission))
    by_code = {p.code: p for p in result.scalars().all()}
    for code, label, category, _ in PERMISSION_CATALOG:
        if code not in by_code:
            permission = Permission(code=code, label=label, category=category)
            db.add(permission)
            by_code[code] = permission
    await db.flush()
    return by_code


async def grant_default_role_permissions(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Flush-only variant (no commit) - lets create_company keep its single
    transaction. Grants each catalog permission's default roles to the company
    ONLY for permissions never seeded for it before."""
    by_code = await _ensure_catalog(db)

    seeded_result = await db.execute(
        select(CompanyPermissionSeed.permission_id).where(CompanyPermissionSeed.company_id == company_id)
    )
    seeded_ids = {row[0] for row in seeded_result.all()}

    grants_result = await db.execute(
        select(RolePermission.role, RolePermission.permission_id).where(RolePermission.company_id == company_id)
    )
    existing_grants = {(row[0].value, row[1]) for row in grants_result.all()}

    for code, _, _, default_roles in PERMISSION_CATALOG:
        permission = by_code[code]
        if permission.id in seeded_ids:
            continue
        for role in default_roles:
            if (role, permission.id) not in existing_grants:
                db.add(RolePermission(company_id=company_id, role=UserRole(role), permission_id=permission.id))
        db.add(CompanyPermissionSeed(company_id=company_id, permission_id=permission.id))
    await db.flush()


async def seed_permission_catalog(db: AsyncSession) -> None:
    """Idempotent - makes the platform-wide catalog match PERMISSION_CATALOG."""
    await _ensure_catalog(db)
    await db.commit()


async def seed_default_role_permissions(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Idempotent, safe on every boot: distributes defaults only for
    permissions this company never received (see grant_default_role_permissions)."""
    await grant_default_role_permissions(db, company_id)
    await db.commit()


async def has_permission(db: AsyncSession, company_id: uuid.UUID, role: str, code: str) -> bool:
    if role == ALWAYS_ALLOWED_ROLE:
        return True
    result = await db.execute(
        select(RolePermission)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role), Permission.code == code)
    )
    return result.scalar_one_or_none() is not None


async def get_permission_matrix(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Every catalog permission with the roles currently granted for this
    company - what the admin screen renders as a checkbox matrix. GESTOR is
    always listed as granted (locked column)."""
    permissions_result = await db.execute(select(Permission).order_by(Permission.category, Permission.label))
    permissions = list(permissions_result.scalars().all())

    grants_result = await db.execute(select(RolePermission).where(RolePermission.company_id == company_id))
    granted_roles_by_permission: dict[uuid.UUID, set[str]] = {}
    for grant in grants_result.scalars().all():
        granted_roles_by_permission.setdefault(grant.permission_id, set()).add(grant.role.value)

    return [
        {
            "id": p.id,
            "code": p.code,
            "label": p.label,
            "category": p.category,
            "granted_roles": sorted(granted_roles_by_permission.get(p.id, set()) | {ALWAYS_ALLOWED_ROLE}),
        }
        for p in permissions
    ]


async def set_role_permission(db: AsyncSession, company_id: uuid.UUID, role: str, permission_id: uuid.UUID, granted: bool) -> None:
    if role == ALWAYS_ALLOWED_ROLE:
        raise ProtectedRoleError("O perfil Gestor tem sempre todas as permissoes e nao pode ser alterado")
    if role not in EDITABLE_ROLES:
        raise ProtectedRoleError("Perfil invalido para configuracao de permissoes")

    existing_result = await db.execute(
        select(RolePermission).where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role), RolePermission.permission_id == permission_id)
    )
    existing = existing_result.scalar_one_or_none()

    if granted and existing is None:
        db.add(RolePermission(company_id=company_id, role=UserRole(role), permission_id=permission_id))
    elif not granted and existing is not None:
        await db.delete(existing)
    await db.commit()


async def list_my_permissions(db: AsyncSession, company_id: uuid.UUID, role: str) -> list[str]:
    """Permission codes granted to this role in this company - what a logged-in
    user calls to show/hide buttons and menu items. GESTOR gets every code."""
    if role == ALWAYS_ALLOWED_ROLE:
        result = await db.execute(select(Permission.code).order_by(Permission.code))
        return [row[0] for row in result.all()]

    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role))
    )
    return [row[0] for row in result.all()]