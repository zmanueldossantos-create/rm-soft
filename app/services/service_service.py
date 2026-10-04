"""
Business logic for Service management (Video 3) - a genuinely separate
sellable entity from Product (see decision: services have no lote/stock/
validade/barcode - a distinct table avoids polluting Product with
irrelevant fields).
Every query is scoped to the caller's company_id (multi-tenant isolation).
"""
from app.services.vat_rule_service import resolve_article_vat
import uuid

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.service import Service
from app.models.vat import VAT


class ServiceAlreadyExistsError(Exception):
    """Raised when a service field (code or name) conflicts within the same company."""
    pass


class ServiceNotFoundError(Exception):
    pass


async def _check_fields_available(
    db: AsyncSession, company_id: uuid.UUID, code: str, name: str, exclude_id: uuid.UUID | None = None,
) -> None:
    code_query = select(Service).where(Service.company_id == company_id, Service.code == code)
    if exclude_id is not None:
        code_query = code_query.where(Service.id != exclude_id)
    if (await db.execute(code_query)).scalar_one_or_none() is not None:
        raise ServiceAlreadyExistsError("Ja existe um servico registado com este codigo")

    name_query = select(Service).where(Service.company_id == company_id, func.lower(Service.name) == name.lower())
    if exclude_id is not None:
        name_query = name_query.where(Service.id != exclude_id)
    if (await db.execute(name_query)).scalar_one_or_none() is not None:
        raise ServiceAlreadyExistsError("Ja existe um servico registado com este nome")


async def create_service(
    db: AsyncSession,
    company_id: uuid.UUID,
    code: str,
    name: str,
    vat_id: uuid.UUID,
    service_type_id: uuid.UUID | None = None,
    resource_type_id: uuid.UUID | None = None,
    description: str | None = None,
    unit_of_measure_id: uuid.UUID | None = None,
    price: float | None = None,
    brand: str | None = None,
    withholding_tax_id: uuid.UUID | None = None,
    not_available_pos: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
    duration_minutes: int | None = None,
) -> Service:
    await _check_fields_available(db, company_id, code, name)
    exemption_reason_id = await resolve_article_vat(db, company_id, vat_id, exemption_reason_id)

    service = Service(
        company_id=company_id, code=code, name=name, vat_id=vat_id,
        service_type_id=service_type_id, resource_type_id=resource_type_id, description=description,
        unit_of_measure_id=unit_of_measure_id, price=price, brand=brand, duration_minutes=duration_minutes,
        withholding_tax_id=withholding_tax_id,
        not_available_pos=not_available_pos, status=status,
        exemption_reason_id=exemption_reason_id,
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


async def list_services(db: AsyncSession, company_id: uuid.UUID) -> list[Service]:
    result = await db.execute(
        select(Service).where(Service.company_id == company_id).order_by(Service.created_at.desc())
    )
    services = list(result.scalars().all())
    # The unit code travels with each article: any screen that can list it (the Caixa included) shows its unit
    # without needing access to the units catalog.
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    unit_ids = {a.unit_of_measure_id for a in services if a.unit_of_measure_id}
    codes = dict((await db.execute(
        select(UnitOfMeasureCatalog.id, UnitOfMeasureCatalog.code).where(UnitOfMeasureCatalog.id.in_(unit_ids))
    )).all()) if unit_ids else {}
    for a in services:
        a.unit_of_measure_code = codes.get(a.unit_of_measure_id)
    return services


async def get_service_or_raise(db: AsyncSession, company_id: uuid.UUID, service_id: uuid.UUID) -> Service:
    result = await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))
    service = result.scalar_one_or_none()
    if service is None:
        raise ServiceNotFoundError("Servico nao encontrado")
    return service


async def update_service(
    db: AsyncSession,
    company_id: uuid.UUID,
    service_id: uuid.UUID,
    code: str,
    name: str,
    vat_id: uuid.UUID,
    service_type_id: uuid.UUID | None = None,
    resource_type_id: uuid.UUID | None = None,
    description: str | None = None,
    unit_of_measure_id: uuid.UUID | None = None,
    price: float | None = None,
    brand: str | None = None,
    withholding_tax_id: uuid.UUID | None = None,
    not_available_pos: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
    duration_minutes: int | None = None,
) -> Service:
    service = await get_service_or_raise(db, company_id, service_id)
    await _check_fields_available(db, company_id, code, name, exclude_id=service_id)
    exemption_reason_id = await resolve_article_vat(db, company_id, vat_id, exemption_reason_id)

    service.code = code
    service.name = name
    service.vat_id = vat_id
    service.service_type_id = service_type_id
    service.resource_type_id = resource_type_id
    service.description = description
    service.unit_of_measure_id = unit_of_measure_id
    service.price = price
    service.duration_minutes = duration_minutes
    service.brand = brand
    service.withholding_tax_id = withholding_tax_id
    service.not_available_pos = not_available_pos
    service.status = status
    service.exemption_reason_id = exemption_reason_id

    await db.commit()
    await db.refresh(service)
    return service


async def toggle_service_status(db: AsyncSession, company_id: uuid.UUID, service_id: uuid.UUID) -> Service:
    service = await get_service_or_raise(db, company_id, service_id)
    service.is_active = not service.is_active
    await db.commit()
    await db.refresh(service)
    return service
