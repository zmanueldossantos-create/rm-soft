"""
Service layer for the dynamic permission system (Permission + RolePermission).
See the models' docstrings for the full design rationale. This is the pilot
implementation - only Consumo Interno's own routes (consumption reasons +
records) are wired to check permissions dynamically for now; every other
route keeps using the older require_role(...) checks until the approach is
validated and rolled out further.

PILOT_PERMISSIONS is the seed catalog - the single source of truth for which
permissions exist and what today's hardcoded require_role(...) equivalent is
per role, reproduced exactly so migrating a route changes nothing for
existing companies until a GESTOR actually edits the matrix in the admin screen.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.permission import Permission
from app.models.role_permission import RolePermission
from app.models.user import UserRole

# (code, label, category, default_roles) - default_roles reproduces the
# hardcoded require_role(...) tuple each route used before migrating.
PILOT_PERMISSIONS: list[tuple[str, str, str, list[str]]] = [
    ("consumption_reasons:view", "Ver motivos de consumo interno", "Consumo Interno", ["GESTOR", "ARMAZENISTA"]),
    ("consumption_reasons:manage", "Criar/editar motivos de consumo interno", "Consumo Interno", ["GESTOR"]),
    ("internal_consumption:view", "Ver historico de consumo interno", "Consumo Interno", ["GESTOR", "ARMAZENISTA"]),
    ("internal_consumption:record", "Registar consumo interno", "Consumo Interno", ["GESTOR", "ARMAZENISTA"]),
]


async def seed_permission_catalog(db: AsyncSession) -> None:
    """Idempotent - inserts any PILOT_PERMISSIONS entry missing from the
    platform-wide Permission catalog. Safe to call repeatedly (e.g. on app
    startup) - does nothing once the catalog is up to date."""
    existing_result = await db.execute(select(Permission.code))
    existing_codes = {row[0] for row in existing_result.all()}

    for code, label, category, _ in PILOT_PERMISSIONS:
        if code not in existing_codes:
            db.add(Permission(code=code, label=label, category=category))
    await db.commit()


async def seed_default_role_permissions(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Grants each PILOT_PERMISSIONS entry to its default roles for one
    company - reproduces the old hardcoded require_role(...) behaviour
    exactly. Call once per company (new company creation, or a one-off
    backfill for companies that existed before this system)."""
    permissions_result = await db.execute(select(Permission).where(Permission.code.in_([p[0] for p in PILOT_PERMISSIONS])))
    permissions_by_code = {p.code: p for p in permissions_result.scalars().all()}

    existing_result = await db.execute(select(RolePermission.role, RolePermission.permission_id).where(RolePermission.company_id == company_id))
    existing_grants = {(row[0].value, row[1]) for row in existing_result.all()}

    for code, _, _, default_roles in PILOT_PERMISSIONS:
        permission = permissions_by_code.get(code)
        if permission is None:
            continue
        for role in default_roles:
            if (role, permission.id) not in existing_grants:
                db.add(RolePermission(company_id=company_id, role=UserRole(role), permission_id=permission.id))
    await db.commit()


async def has_permission(db: AsyncSession, company_id: uuid.UUID, role: str, code: str) -> bool:
    result = await db.execute(
        select(RolePermission)
        .join(Permission, Permission.id == RolePermission.permission_id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role), Permission.code == code)
    )
    return result.scalar_one_or_none() is not None


async def get_permission_matrix(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Returns every PILOT_PERMISSIONS entry with the set of roles currently
    granted for this company - what the admin screen renders as a checkbox
    matrix."""
    permissions_result = await db.execute(select(Permission).order_by(Permission.category, Permission.label))
    permissions = list(permissions_result.scalars().all())

    grants_result = await db.execute(select(RolePermission).where(RolePermission.company_id == company_id))
    grants = list(grants_result.scalars().all())
    granted_roles_by_permission: dict[uuid.UUID, set[str]] = {}
    for grant in grants:
        granted_roles_by_permission.setdefault(grant.permission_id, set()).add(grant.role.value)

    return [
        {
            "id": p.id,
            "code": p.code,
            "label": p.label,
            "category": p.category,
            "granted_roles": sorted(granted_roles_by_permission.get(p.id, set())),
        }
        for p in permissions
    ]


async def set_role_permission(db: AsyncSession, company_id: uuid.UUID, role: str, permission_id: uuid.UUID, granted: bool) -> None:
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
    """Returns the permission codes currently granted to this role in this
    company - what a logged-in user calls to know their own dynamic access
    (e.g. to show/hide a button), as opposed to get_permission_matrix which
    is the full admin view across all roles."""
    result = await db.execute(
        select(Permission.code)
        .join(RolePermission, RolePermission.permission_id == Permission.id)
        .where(RolePermission.company_id == company_id, RolePermission.role == UserRole(role))
    )
    return [row[0] for row in result.all()]
