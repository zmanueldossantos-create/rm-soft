"""
Tests for the sector / capability catalog: every permission is classified, dependencies are
consistent, the seed is idempotent and never overwrites the SUPER_ADMIN's choices, sectors in
development cannot be granted, and the overview reports what is active (and what is off while
data exists).
"""
from collections import defaultdict

import pytest
from sqlalchemy import func, select

from app.core.capabilities import (
    CAPABILITIES, CORE, CORE_PREFIXES, SECTORS, SECTORS_BY_CODE, capability_of_permission, expand_dependencies,
)
from app.models.company import Company
from app.models.company_module import CompanyModule
from app.models.module import Module
from app.models.module_capability import ModuleCapability
from app.services.company_module_service import set_company_modules
from app.services.company_service import create_company
from app.services.open_account_service import open_account
from app.services.permission_service import PERMISSION_CATALOG
from app.services.sector_service import (
    ModuleNotAvailableError, UnknownCapabilityError, build_overview, get_company_capabilities,
    reset_module_capabilities, seed_sector_catalog, set_module_capabilities,
)


async def _module(db, code):
    return (await db.execute(select(Module).where(Module.code == code))).scalar_one()


async def _enabled(db, module_id):
    rows = await db.execute(
        select(ModuleCapability.capability).where(ModuleCapability.module_id == module_id, ModuleCapability.is_enabled.is_(True))
    )
    return {r[0] for r in rows.all()}


def test_every_permission_is_classified():
    """A permission whose prefix is neither core nor owned by a capability raises KeyError -
    classify it in app.core.capabilities."""
    per_capability = defaultdict(int)
    used_prefixes = set()
    for code, _label, _category, _roles in PERMISSION_CATALOG:
        per_capability[capability_of_permission(code)] += 1
        used_prefixes.add(code.split(":", 1)[0])
    for capability in CAPABILITIES:
        assert per_capability[capability] > 0, f"capability {capability} owns no permission"
    assert per_capability[CORE] > 0
    prefixes = [p for c in CAPABILITIES.values() for p in c.prefixes]
    assert len(prefixes) == len(set(prefixes)), "a prefix belongs to two capabilities"
    assert not set(prefixes) & CORE_PREFIXES, "a prefix is both core and capability"
    assert not CORE_PREFIXES - used_prefixes, "core prefixes no permission uses: " + str(sorted(CORE_PREFIXES - used_prefixes))


def test_capability_dependencies_are_consistent():
    for capability in CAPABILITIES.values():
        for required in capability.requires:
            assert required in CAPABILITIES, (capability.code, required)
        assert capability.code not in expand_dependencies(capability.requires), "dependency cycle at " + capability.code
    codes = [s.code for s in SECTORS]
    assert len(codes) == len(set(codes))
    for sector in SECTORS:
        assert set(sector.capabilities) <= set(CAPABILITIES), sector.code
        assert expand_dependencies(set(sector.capabilities)) == set(sector.capabilities), "defaults not closed: " + sector.code
        assert sector.ready or sector.ready_note, "a sector in development needs a note: " + sector.code


@pytest.mark.asyncio
async def test_seed_matches_existing_modules_creates_the_rest_and_is_idempotent(db):
    db.add_all([Module(name="Hotel"), Module(name="Bar")])
    await db.commit()

    await seed_sector_catalog(db)
    modules = (await db.execute(select(Module))).scalars().all()
    assert len(modules) == len(SECTORS)
    assert {m.code for m in modules} == {s.code for s in SECTORS}
    hotel, bar = await _module(db, "HOTEL"), await _module(db, "BAR")
    hotel_id, bar_id = hotel.id, bar.id
    assert await _enabled(db, hotel_id) == set(SECTORS_BY_CODE["HOTEL"].capabilities)

    await set_module_capabilities(db, bar_id, ["STOCK"])  # the SUPER_ADMIN edits Bar
    await seed_sector_catalog(db)  # a later boot must not undo it
    assert await _enabled(db, bar_id) == {"STOCK"}
    assert (await db.execute(select(func.count()).select_from(Module))).scalar_one() == len(SECTORS)
    assert (await db.execute(select(func.count()).select_from(ModuleCapability))).scalar_one() == len(SECTORS) * len(CAPABILITIES)


@pytest.mark.asyncio
async def test_set_capabilities_adds_dependencies_and_keeps_every_row(db):
    await seed_sector_catalog(db)
    spa = await _module(db, "SPA_SALAO")
    spa_id = spa.id
    result = await set_module_capabilities(db, spa_id, ["HOTEL_STAY"])
    assert set(result) == {"HOTEL_STAY", "BOOKINGS", "RESOURCES", "OPEN_ACCOUNTS"}
    assert await _enabled(db, spa_id) == set(result)
    rows = (await db.execute(select(ModuleCapability).where(ModuleCapability.module_id == spa_id))).scalars().all()
    assert len(rows) == len(CAPABILITIES)  # switched-off capabilities stay as rows

    with pytest.raises(UnknownCapabilityError):
        await set_module_capabilities(db, spa_id, ["NOPE"])
    assert await _enabled(db, spa_id) == set(result)

    reset = await reset_module_capabilities(db, spa_id)
    assert set(reset) == set(SECTORS_BY_CODE["SPA_SALAO"].capabilities)


@pytest.mark.asyncio
async def test_sectors_in_development_cannot_be_granted(db, company_with_essentials):
    await seed_sector_catalog(db)
    company_id = company_with_essentials["company"].id
    pharmacy, bakery = await _module(db, "FARMACIA"), await _module(db, "PADARIA")
    pharmacy_id, bakery_id = pharmacy.id, bakery.id
    before = (await db.execute(select(func.count()).select_from(CompanyModule).where(CompanyModule.company_id == company_id))).scalar_one()

    with pytest.raises(ModuleNotAvailableError):
        await set_company_modules(db, company_id, [pharmacy_id])
    after = (await db.execute(select(func.count()).select_from(CompanyModule).where(CompanyModule.company_id == company_id))).scalar_one()
    assert after == before

    await set_company_modules(db, company_id, [bakery_id])  # a ready sector is fine


@pytest.mark.asyncio
async def test_create_company_refuses_a_sector_in_development(db):
    await seed_sector_catalog(db)
    pharmacy = await _module(db, "FARMACIA")
    with pytest.raises(ModuleNotAvailableError):
        await create_company(
            db, name="Farmacia Teste Lda", nif="5000123999", email="farmacia@teste.co.ao", phone_number="+244923000101",
            gestor_full_name="Gestor Farmacia", gestor_phone_number="+244923000102", gestor_password="Teste@2026",
            module_ids=[pharmacy.id],
        )
    assert (await db.execute(select(func.count()).select_from(Company).where(Company.nif == "5000123999"))).scalar_one() == 0


@pytest.mark.asyncio
async def test_company_capabilities_are_the_union_of_its_active_modules(db, company_with_essentials):
    await seed_sector_catalog(db)
    company_id = company_with_essentials["company"].id
    hotel, bakery = await _module(db, "HOTEL"), await _module(db, "PADARIA")
    hotel_id, bakery_id = hotel.id, bakery.id
    hotel_caps = set(SECTORS_BY_CODE["HOTEL"].capabilities)
    bakery_caps = set(SECTORS_BY_CODE["PADARIA"].capabilities)

    await set_company_modules(db, company_id, [hotel_id, bakery_id])
    assert await get_company_capabilities(db, company_id) == hotel_caps | bakery_caps

    await set_company_modules(db, company_id, [bakery_id])  # revoke Hotel
    assert await get_company_capabilities(db, company_id) == bakery_caps
    grant = (await db.execute(
        select(CompanyModule).where(CompanyModule.company_id == company_id, CompanyModule.module_id == hotel_id)
    )).scalar_one()
    assert grant.is_enabled is False  # revoked, never deleted


@pytest.mark.asyncio
async def test_overview_flags_inactive_capabilities_that_still_have_data(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    await seed_sector_catalog(db)
    await open_account(db, company_id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Mesa 1")

    overview = await build_overview(db)
    assert len(overview["modules"]) >= len(SECTORS)
    company = next(c for c in overview["companies"] if c["id"] == company_id)
    entry = next(x for x in company["capabilities"] if x["code"] == "OPEN_ACCOUNTS")
    assert entry["active"] is False and entry["data_count"] == 1 and entry["inactive_with_data"] is True
    assert any(i["company_id"] == company_id and i["capability"] == "OPEN_ACCOUNTS" for i in overview["impact"])

    bar = await _module(db, "BAR")
    await set_company_modules(db, company_id, [bar.id])
    overview = await build_overview(db)
    company = next(c for c in overview["companies"] if c["id"] == company_id)
    entry = next(x for x in company["capabilities"] if x["code"] == "OPEN_ACCOUNTS")
    assert entry["active"] is True and entry["via"] == ["Bar"] and entry["inactive_with_data"] is False
    assert not any(i["company_id"] == company_id and i["capability"] == "OPEN_ACCOUNTS" for i in overview["impact"])