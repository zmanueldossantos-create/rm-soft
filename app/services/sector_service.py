"""
Sector / capability service: seeds the sector catalog into the Module table, edits which
capabilities a module gives, computes what a company can use (the union of the capabilities of
its granted, enabled, active modules) and builds the SUPER_ADMIN overview.

Nothing here ever deletes data: turning a capability off only flips is_enabled.
"""
import unicodedata
import uuid
from collections import defaultdict

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.capabilities import CAPABILITIES, CORE, SECTORS, SECTORS_BY_CODE, capability_of_permission, expand_dependencies
from app.core.config import get_settings
from app.models.activity import Activity
from app.models.company import Company
from app.models.company_module import CompanyModule
from app.models.module import Module
from app.models.module_capability import ModuleCapability
from app.services.module_service import get_module_or_raise
from app.services.permission_service import PERMISSION_CATALOG

# Rows of real data per capability and company - lets the overview flag a capability that is
# switched off although the company already has data in it.
DATA_COUNT_SQL = {
    "STOCK": "SELECT company_id, count(*) FROM stock_movements GROUP BY company_id",
    "PRODUCTION": "SELECT company_id, count(*) FROM recipe_ingredients GROUP BY company_id",
    "RESOURCES": "SELECT company_id, count(*) FROM resources GROUP BY company_id",
    "BOOKINGS": "SELECT company_id, count(*) FROM bookings GROUP BY company_id",
    "OPEN_ACCOUNTS": "SELECT company_id, count(*) FROM open_accounts GROUP BY company_id",
    "HOTEL_STAY": "SELECT company_id, count(*) FROM open_accounts WHERE booking_id IS NOT NULL GROUP BY company_id",
}


class ModuleNotAvailableError(Exception):
    """A module (sector) still in development cannot be granted to a company."""


class UnknownCapabilityError(Exception):
    pass


class NoSectorDefaultsError(Exception):
    pass


def _norm(value: str) -> str:
    stripped = "".join(c for c in unicodedata.normalize("NFKD", value) if not unicodedata.combining(c))
    return " ".join(stripped.casefold().split())


async def seed_sector_catalog(db: AsyncSession) -> None:
    """Idempotent. Makes sure every sector of app.core.capabilities exists as a Module (an
    existing module is matched by name, ignoring case and accents, and gets its code) and that
    each module coded from the catalog has its capability rows. Default capabilities are
    written ONCE per module: what the SUPER_ADMIN changes afterwards is never overwritten."""
    modules = list((await db.execute(select(Module))).scalars().all())
    by_code = {m.code: m for m in modules if m.code}
    uncoded = {_norm(m.name): m for m in modules if not m.code}
    for sector in SECTORS:
        if sector.code in by_code:
            continue
        module = uncoded.pop(_norm(sector.name), None)
        if module is not None:
            module.code = sector.code
        else:
            module = Module(name=sector.name, description=sector.description, code=sector.code)
            db.add(module)
        by_code[sector.code] = module
    await db.flush()

    seeded = {row[0] for row in (await db.execute(select(ModuleCapability.module_id))).all()}
    for sector in SECTORS:
        module = by_code[sector.code]
        if module.id in seeded:
            continue
        for code in CAPABILITIES:
            db.add(ModuleCapability(module_id=module.id, capability=code, is_enabled=code in sector.capabilities))
    await db.commit()


async def ensure_modules_grantable(db: AsyncSession, module_ids) -> None:
    """Refuses modules whose sector is still in development."""
    ids = list(module_ids or [])
    if not ids:
        return
    result = await db.execute(select(Module).where(Module.id.in_(ids)))
    for module in result.scalars().all():
        sector = SECTORS_BY_CODE.get(module.code) if module.code else None
        if sector is not None and not sector.ready:
            raise ModuleNotAvailableError(f"O modulo {module.name} ainda esta em desenvolvimento e nao pode ser ativado")


async def _write_capabilities(db: AsyncSession, module_id: uuid.UUID, enabled: set[str]) -> None:
    rows = (await db.execute(select(ModuleCapability).where(ModuleCapability.module_id == module_id))).scalars().all()
    by_code = {r.capability: r for r in rows}
    for code in CAPABILITIES:
        row = by_code.get(code)
        if row is None:
            db.add(ModuleCapability(module_id=module_id, capability=code, is_enabled=code in enabled))
        else:
            row.is_enabled = code in enabled


async def set_module_capabilities(db: AsyncSession, module_id: uuid.UUID, codes: list[str]) -> list[str]:
    """Sets exactly these capabilities (plus whatever they require) on a module. Every
    capability keeps its row - the others are just switched off."""
    module = await get_module_or_raise(db, module_id)
    unknown = sorted(c for c in codes if c not in CAPABILITIES)
    if unknown:
        raise UnknownCapabilityError("Funcao desconhecida: " + ", ".join(unknown))
    wanted = expand_dependencies(set(codes))
    await _write_capabilities(db, module.id, wanted)
    await db.commit()
    return sorted(wanted)


async def reset_module_capabilities(db: AsyncSession, module_id: uuid.UUID) -> list[str]:
    """Back to the default capabilities of the module's sector."""
    module = await get_module_or_raise(db, module_id)
    sector = SECTORS_BY_CODE.get(module.code) if module.code else None
    if sector is None:
        raise NoSectorDefaultsError("Este modulo nao tem funcoes padrao")
    wanted = expand_dependencies(set(sector.capabilities))
    await _write_capabilities(db, module.id, wanted)
    await db.commit()
    return sorted(wanted)


async def _capability_sources(db: AsyncSession, company_id: uuid.UUID | None = None):
    """company_id -> capability -> names of the active, granted modules that give it."""
    query = (
        select(CompanyModule.company_id, Module.name, ModuleCapability.capability)
        .join(Module, Module.id == CompanyModule.module_id)
        .join(ModuleCapability, ModuleCapability.module_id == Module.id)
        .where(CompanyModule.is_enabled.is_(True), Module.is_active.is_(True), ModuleCapability.is_enabled.is_(True))
    )
    if company_id is not None:
        query = query.where(CompanyModule.company_id == company_id)
    sources = defaultdict(lambda: defaultdict(list))
    for cid, module_name, capability in (await db.execute(query)).all():
        if module_name not in sources[cid][capability]:
            sources[cid][capability].append(module_name)
    return sources


async def get_company_capabilities(db: AsyncSession, company_id: uuid.UUID) -> set[str]:
    """Capabilities a company can use: the union of its granted, enabled, active modules'."""
    sources = await _capability_sources(db, company_id)
    return set(sources[company_id])


async def _data_counts(db: AsyncSession) -> dict:
    counts = {}
    for capability, sql in DATA_COUNT_SQL.items():
        counts[capability] = {row[0]: int(row[1]) for row in (await db.execute(text(sql))).all()}
    return counts


async def build_overview(db: AsyncSession) -> dict:
    """Everything the SUPER_ADMIN overview screen shows: capabilities, modules (sectors),
    companies with what is active for each, and the impact list (a capability that is off
    while the company already has data in it)."""
    modules = list((await db.execute(select(Module))).scalars().all())
    order = {s.code: i for i, s in enumerate(SECTORS)}
    modules.sort(key=lambda m: (order.get(m.code, 999), m.name))
    companies = list((await db.execute(select(Company).order_by(Company.name))).scalars().all())
    grants = list((await db.execute(select(CompanyModule))).scalars().all())
    activities = list((await db.execute(select(Activity))).scalars().all())
    capability_rows = list((await db.execute(select(ModuleCapability))).scalars().all())
    sources = await _capability_sources(db)
    counts = await _data_counts(db)

    module_by_id = {m.id: m for m in modules}
    enabled_by_module = defaultdict(set)
    for row in capability_rows:
        if row.is_enabled:
            enabled_by_module[row.module_id].add(row.capability)

    permissions_by_capability = defaultdict(list)
    for code, _label, _category, _roles in PERMISSION_CATALOG:
        permissions_by_capability[capability_of_permission(code)].append(code)

    granted_count = defaultdict(int)
    grants_by_company = defaultdict(list)
    for grant in grants:
        grants_by_company[grant.company_id].append(grant)
        if grant.is_enabled:
            granted_count[grant.module_id] += 1

    activities_by_company = defaultdict(list)
    for activity in activities:
        module = module_by_id.get(activity.module_id)
        activities_by_company[activity.company_id].append(
            {"name": activity.name, "module": module.name if module else None, "is_active": activity.is_active}
        )

    active_companies = defaultdict(int)
    company_entries, impact = [], []
    for company in companies:
        company_sources = sources.get(company.id, {})
        capability_entries = []
        for code in CAPABILITIES:
            via = list(company_sources.get(code, []))
            data_count = counts[code].get(company.id, 0)
            active = bool(via)
            inactive_with_data = (not active) and data_count > 0
            if active:
                active_companies[code] += 1
            if inactive_with_data:
                impact.append({"company_id": company.id, "company": company.name, "capability": code, "data_count": data_count})
            capability_entries.append({
                "code": code, "active": active, "via": via, "data_count": data_count, "inactive_with_data": inactive_with_data,
            })
        company_entries.append({
            "id": company.id,
            "name": company.name,
            "is_active": company.is_active,
            "modules": [
                {"id": g.module_id, "name": module_by_id[g.module_id].name, "is_enabled": g.is_enabled}
                for g in grants_by_company.get(company.id, []) if g.module_id in module_by_id
            ],
            "capabilities": capability_entries,
            "activities": activities_by_company.get(company.id, []),
        })

    module_entries = []
    for module in modules:
        sector = SECTORS_BY_CODE.get(module.code) if module.code else None
        module_entries.append({
            "id": module.id,
            "name": module.name,
            "code": module.code,
            "description": module.description,
            "is_active": module.is_active,
            "is_ready": True if sector is None else sector.ready,
            "ready_note": sector.ready_note if sector else "",
            "capabilities": sorted(enabled_by_module.get(module.id, set())),
            "companies_granted": granted_count.get(module.id, 0),
        })

    capability_entries = []
    for code, capability in CAPABILITIES.items():
        capability_entries.append({
            "code": code,
            "label": capability.label,
            "description": capability.description,
            "requires": list(capability.requires),
            "permissions": permissions_by_capability.get(code, []),
            "screens": list(capability.screens),
            "modules": [m.name for m in modules if m.is_active and code in enabled_by_module.get(m.id, set())],
            "companies_active": active_companies.get(code, 0),
        })

    return {
        "enforce_capabilities": get_settings().ENFORCE_CAPABILITIES,
        "core": {"label": "Nucleo", "permissions": permissions_by_capability.get(CORE, [])},
        "capabilities": capability_entries,
        "modules": module_entries,
        "companies": company_entries,
        "impact": sorted(impact, key=lambda i: (i["company"], i["capability"])),
    }