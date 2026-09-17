"""
Business logic for Service management (Video 3) - a genuinely separate
sellable entity from Product (see decision: services have no lote/stock/
validade/barcode - a distinct table avoids polluting Product with
irrelevant fields).
Every query is scoped to the caller's company_id (multi-tenant isolation).
"""
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


class ExemptionReasonRequiredError(Exception):
    """Raised when the chosen VAT rate is 0% (isento) but no AGT exemption reason code was given."""
    pass


async def _check_exemption_reason(db: AsyncSession, vat_id: uuid.UUID, exemption_reason_id: uuid.UUID | None) -> None:
    result = await db.execute(select(VAT).where(VAT.id == vat_id))
    vat = result.scalar_one_or_none()
    if vat is not None and float(vat.rate) == 0 and exemption_reason_id is None:
        raise ExemptionReasonRequiredError("Motivo de isencao obrigatorio quando o IVA e 0% (isento)")


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
    subject_to_return: bool = False,
    not_available_pos: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Service:
    await _check_fields_available(db, company_id, code, name)
    await _check_exemption_reason(db, vat_id, exemption_reason_id)

    service = Service(
        company_id=company_id, code=code, name=name, vat_id=vat_id,
        service_type_id=service_type_id, resource_type_id=resource_type_id, description=description,
        unit_of_measure_id=unit_of_measure_id, price=price, brand=brand,
        withholding_tax_id=withholding_tax_id, subject_to_return=subject_to_return,
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
    return list(result.scalars().all())


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
    subject_to_return: bool = False,
    not_available_pos: bool = False,
    status: str = "ACTIVO",
    exemption_reason_id: uuid.UUID | None = None,
) -> Service:
    service = await get_service_or_raise(db, company_id, service_id)
    await _check_fields_available(db, company_id, code, name, exclude_id=service_id)
    await _check_exemption_reason(db, vat_id, exemption_reason_id)

    service.code = code
    service.name = name
    service.vat_id = vat_id
    service.service_type_id = service_type_id
    service.resource_type_id = resource_type_id
    service.description = description
    service.unit_of_measure_id = unit_of_measure_id
    service.price = price
    service.brand = brand
    service.withholding_tax_id = withholding_tax_id
    service.subject_to_return = subject_to_return
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
