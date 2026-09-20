"""
Business logic for granting/revoking Company access to Modules -
SUPER_ADMIN only. The GESTOR can only create Activities for modules
granted here (see activity_service).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company_module import CompanyModule
from app.models.module import Module
from app.services.sector_service import ensure_modules_grantable


async def list_company_modules(db: AsyncSession, company_id: uuid.UUID) -> list[Module]:
    """Returns the Modules granted (and enabled) to this company."""
    result = await db.execute(
        select(Module)
        .join(CompanyModule, CompanyModule.module_id == Module.id)
        .where(CompanyModule.company_id == company_id, CompanyModule.is_enabled == True)
        .order_by(Module.name)
    )
    return list(result.scalars().all())


async def set_company_modules(db: AsyncSession, company_id: uuid.UUID, module_ids: list[uuid.UUID]) -> None:
    """
    Replaces the company's granted modules with exactly this set - used
    both at company creation and from the modules management screen.
    Does not delete existing Activities if a module is later revoked
    (historical invoices must remain intact); it only blocks NEW Activity
    creation for modules no longer granted.
    """
    await ensure_modules_grantable(db, module_ids)
    existing_result = await db.execute(select(CompanyModule).where(CompanyModule.company_id == company_id))
    existing = {cm.module_id: cm for cm in existing_result.scalars().all()}

    for module_id in module_ids:
        if module_id in existing:
            existing[module_id].is_enabled = True
        else:
            db.add(CompanyModule(company_id=company_id, module_id=module_id, is_enabled=True))

    for module_id, cm in existing.items():
        if module_id not in module_ids:
            cm.is_enabled = False

    await db.commit()


async def is_module_granted(db: AsyncSession, company_id: uuid.UUID, module_id: uuid.UUID) -> bool:
    result = await db.execute(
        select(CompanyModule).where(
            CompanyModule.company_id == company_id,
            CompanyModule.module_id == module_id,
            CompanyModule.is_enabled == True,
        )
    )
    return result.scalar_one_or_none() is not None
