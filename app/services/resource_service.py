"""
Service layer for Resource - the generic bookable "thing" (room, therapist,
table...) behind the Booking system. See app.models.resource for the full
design rationale.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import Resource
from app.services.activity_service import get_activity_or_raise
from app.services.resource_type_service import get_resource_type_or_raise


class ResourceNotFoundError(Exception):
    pass


async def create_resource(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID, resource_type_id: uuid.UUID, name: str,
    capacity: int | None = None,
) -> Resource:
    await get_activity_or_raise(db, company_id, activity_id)
    await get_resource_type_or_raise(db, company_id, resource_type_id)
    resource = Resource(company_id=company_id, activity_id=activity_id, resource_type_id=resource_type_id, name=name, capacity=capacity)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


async def get_resource_or_raise(db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID) -> Resource:
    result = await db.execute(select(Resource).where(Resource.id == resource_id, Resource.company_id == company_id))
    resource = result.scalar_one_or_none()
    if resource is None:
        raise ResourceNotFoundError("Recurso nao encontrado")
    return resource


async def list_resources(
    db: AsyncSession, company_id: uuid.UUID, activity_id: uuid.UUID | None = None, resource_type_id: uuid.UUID | None = None,
) -> list[Resource]:
    query = select(Resource).where(Resource.company_id == company_id)
    if activity_id is not None:
        query = query.where(Resource.activity_id == activity_id)
    if resource_type_id is not None:
        query = query.where(Resource.resource_type_id == resource_type_id)
    result = await db.execute(query.order_by(Resource.name))
    return list(result.scalars().all())


async def update_resource(
    db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID, name: str, capacity: int | None = None,
) -> Resource:
    resource = await get_resource_or_raise(db, company_id, resource_id)
    resource.name = name
    resource.capacity = capacity
    await db.commit()
    await db.refresh(resource)
    return resource


async def toggle_resource_status(db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID) -> Resource:
    resource = await get_resource_or_raise(db, company_id, resource_id)
    resource.is_active = not resource.is_active
    await db.commit()
    await db.refresh(resource)
    return resource
