"""
Business logic for the Module catalog (SUPER_ADMIN only, platform-wide).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.module import Module


class ModuleNotFoundError(Exception):
    pass


async def list_modules(db: AsyncSession) -> list[Module]:
    result = await db.execute(select(Module).order_by(Module.name))
    return list(result.scalars().all())


async def create_module(db: AsyncSession, name: str, description: str | None) -> Module:
    module = Module(name=name, description=description)
    db.add(module)
    await db.commit()
    await db.refresh(module)
    return module


async def get_module_or_raise(db: AsyncSession, module_id: uuid.UUID) -> Module:
    result = await db.execute(select(Module).where(Module.id == module_id))
    module = result.scalar_one_or_none()
    if module is None:
        raise ModuleNotFoundError("Modulo nao encontrado")
    return module


async def update_module(db: AsyncSession, module_id: uuid.UUID, name: str, description: str | None) -> Module:
    module = await get_module_or_raise(db, module_id)
    module.name = name
    module.description = description
    await db.commit()
    await db.refresh(module)
    return module


async def toggle_module_status(db: AsyncSession, module_id: uuid.UUID) -> Module:
    module = await get_module_or_raise(db, module_id)
    module.is_active = not module.is_active
    await db.commit()
    await db.refresh(module)
    return module
