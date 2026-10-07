"""
Service layer for ResourceTypeCatalog - the managed catalog of resource
types (Chambre, Praticien, Mesa...). See app.models.resource_type_catalog
for the full design rationale.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource_type_catalog import ResourceTypeCatalog


class ResourceTypeNotFoundError(Exception):
    pass


class ResourceTypeAlreadyExistsError(Exception):
    pass


async def create_resource_type(db: AsyncSession, company_id: uuid.UUID, name: str, requires_service: bool = False) -> ResourceTypeCatalog:
    existing_result = await db.execute(
        select(ResourceTypeCatalog).where(ResourceTypeCatalog.company_id == company_id, ResourceTypeCatalog.name == name)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise ResourceTypeAlreadyExistsError(f"Ja existe um tipo de recurso chamado '{name}'")

    resource_type = ResourceTypeCatalog(company_id=company_id, name=name, requires_service=requires_service)
    db.add(resource_type)
    await db.commit()
    await db.refresh(resource_type)
    return resource_type


async def get_resource_type_or_raise(db: AsyncSession, company_id: uuid.UUID, resource_type_id: uuid.UUID) -> ResourceTypeCatalog:
    result = await db.execute(
        select(ResourceTypeCatalog).where(ResourceTypeCatalog.id == resource_type_id, ResourceTypeCatalog.company_id == company_id)
    )
    resource_type = result.scalar_one_or_none()
    if resource_type is None:
        raise ResourceTypeNotFoundError("Tipo de recurso nao encontrado")
    return resource_type


async def list_resource_types(db: AsyncSession, company_id: uuid.UUID) -> list[ResourceTypeCatalog]:
    result = await db.execute(select(ResourceTypeCatalog).where(ResourceTypeCatalog.company_id == company_id).order_by(ResourceTypeCatalog.name))
    return list(result.scalars().all())


async def update_resource_type(db: AsyncSession, company_id: uuid.UUID, resource_type_id: uuid.UUID, name: str, requires_service: bool = False) -> ResourceTypeCatalog:
    resource_type = await get_resource_type_or_raise(db, company_id, resource_type_id)
    if name != resource_type.name:
        existing_result = await db.execute(
            select(ResourceTypeCatalog).where(ResourceTypeCatalog.company_id == company_id, ResourceTypeCatalog.name == name, ResourceTypeCatalog.id != resource_type_id)
        )
        if existing_result.scalar_one_or_none() is not None:
            raise ResourceTypeAlreadyExistsError(f"Ja existe um tipo de recurso chamado '{name}'")
    resource_type.name = name
    resource_type.requires_service = requires_service
    await db.commit()
    await db.refresh(resource_type)
    return resource_type


async def toggle_resource_type_status(db: AsyncSession, company_id: uuid.UUID, resource_type_id: uuid.UUID) -> ResourceTypeCatalog:
    resource_type = await get_resource_type_or_raise(db, company_id, resource_type_id)
    resource_type.is_active = not resource_type.is_active
    await db.commit()
    await db.refresh(resource_type)
    return resource_type
