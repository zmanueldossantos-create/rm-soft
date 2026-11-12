"""
Service layer for Resource - the generic bookable "thing" (room, therapist,
table...) behind the Booking system. See app.models.resource for the full
design rationale.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resource import Resource, ResourceRatePrice
from app.services.activity_service import get_activity_or_raise
from app.services.resource_type_service import get_resource_type_or_raise


class ResourceNotFoundError(Exception):
    pass


class InvalidRatePriceError(Exception):
    """A resource's own price that cannot be kept (a rate of another type, a negative price...)."""


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
        raise ResourceNotFoundError("Recurso não encontrado")
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


# ---------- a resource's own prices for the rates of its type ----------

async def attach_rate_prices(db: AsyncSession, resources: list[Resource]) -> list[Resource]:
    """Each resource with .rate_prices {service id: price} - its own prices (the screens show them)."""
    ids = [r.id for r in resources]
    prices: dict = {}
    if ids:
        for row in (await db.execute(select(ResourceRatePrice).where(ResourceRatePrice.resource_id.in_(ids)))).scalars().all():
            prices.setdefault(row.resource_id, {})[row.service_id] = float(row.price)
    for r in resources:
        r.rate_prices = prices.get(r.id, {})
    return resources


async def resource_rate_price(db: AsyncSession, resource_id: uuid.UUID | None, service) -> float:
    """The price of a rate sold with this resource: its own, else the rate's."""
    if resource_id is not None:
        own = (await db.execute(select(ResourceRatePrice.price).where(
            ResourceRatePrice.resource_id == resource_id, ResourceRatePrice.service_id == service.id))).scalar_one_or_none()
        if own is not None:
            return float(own)
    return float(service.price or 0)


async def set_rate_prices(db: AsyncSession, company_id: uuid.UUID, resource_id: uuid.UUID, prices: list[dict]) -> Resource:
    """Replaces the resource's own prices: [{service_id, price}] - a rate of its type each; a price left empty (None)
    means the rate's own price."""
    from app.models.service import Service
    resource = await get_resource_or_raise(db, company_id, resource_id)
    rates = {s.id: s for s in (await db.execute(select(Service).where(
        Service.company_id == company_id, Service.resource_type_id == resource.resource_type_id))).scalars().all()}
    wanted = {}
    for item in prices:
        service_id, price = uuid.UUID(str(item["service_id"])), item.get("price")
        if service_id not in rates:
            raise InvalidRatePriceError("Só uma tarifa do tipo deste recurso pode ter preço próprio")
        if price is None:
            continue
        if float(price) < 0:
            raise InvalidRatePriceError(f"{rates[service_id].name}: o preço não pode ser negativo")
        wanted[service_id] = round(float(price), 2)
    existing = {row.service_id: row for row in (await db.execute(select(ResourceRatePrice).where(
        ResourceRatePrice.resource_id == resource.id))).scalars().all()}
    for service_id, row in existing.items():
        if service_id not in wanted:
            await db.delete(row)
    for service_id, price in wanted.items():
        if service_id in existing:
            existing[service_id].price = price
        else:
            db.add(ResourceRatePrice(company_id=company_id, resource_id=resource.id, service_id=service_id, price=price))
    await db.commit()
    await db.refresh(resource)
    return (await attach_rate_prices(db, [resource]))[0]
