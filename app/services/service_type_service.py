"""
Business logic for ServiceType - company-scoped catalog (Video 3),
managed by the company's own GESTOR (not SUPER_ADMIN).
"""
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service_type import ServiceType


class ServiceTypeNotFoundError(Exception):
    pass


class ServiceTypeAlreadyExistsError(Exception):
    pass


async def _check_name_available(db: AsyncSession, company_id: uuid.UUID, name: str, exclude_id: uuid.UUID | None = None) -> None:
    query = select(ServiceType).where(ServiceType.company_id == company_id, func.lower(ServiceType.name) == name.lower())
    if exclude_id is not None:
        query = query.where(ServiceType.id != exclude_id)
    if (await db.execute(query)).scalar_one_or_none() is not None:
        raise ServiceTypeAlreadyExistsError("Ja existe um tipo de servico com este nome")


async def list_service_types(db: AsyncSession, company_id: uuid.UUID) -> list[ServiceType]:
    result = await db.execute(
        select(ServiceType).where(ServiceType.company_id == company_id).order_by(ServiceType.name)
    )
    return list(result.scalars().all())


async def create_service_type(
    db: AsyncSession, company_id: uuid.UUID, name: str,
    not_available_purchases: bool = False, not_available_pos: bool = False, not_available_sales: bool = False,
) -> ServiceType:
    await _check_name_available(db, company_id, name)
    service_type = ServiceType(
        company_id=company_id, name=name,
        not_available_purchases=not_available_purchases,
        not_available_pos=not_available_pos,
        not_available_sales=not_available_sales,
    )
    db.add(service_type)
    await db.commit()
    await db.refresh(service_type)
    return service_type


async def update_service_type(
    db: AsyncSession, company_id: uuid.UUID, service_type_id: uuid.UUID, name: str,
    not_available_purchases: bool = False, not_available_pos: bool = False, not_available_sales: bool = False,
) -> ServiceType:
    result = await db.execute(select(ServiceType).where(ServiceType.id == service_type_id, ServiceType.company_id == company_id))
    service_type = result.scalar_one_or_none()
    if service_type is None:
        raise ServiceTypeNotFoundError("Tipo de servico nao encontrado")
    await _check_name_available(db, company_id, name, exclude_id=service_type_id)
    service_type.name = name
    service_type.not_available_purchases = not_available_purchases
    service_type.not_available_pos = not_available_pos
    service_type.not_available_sales = not_available_sales
    await db.commit()
    await db.refresh(service_type)
    return service_type


async def toggle_service_type(db: AsyncSession, company_id: uuid.UUID, service_type_id: uuid.UUID) -> ServiceType:
    result = await db.execute(select(ServiceType).where(ServiceType.id == service_type_id, ServiceType.company_id == company_id))
    service_type = result.scalar_one_or_none()
    if service_type is None:
        raise ServiceTypeNotFoundError("Tipo de servico nao encontrado")
    service_type.is_active = not service_type.is_active
    await db.commit()
    await db.refresh(service_type)
    return service_type
