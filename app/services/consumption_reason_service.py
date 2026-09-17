"""
Service layer for ConsumptionReasonCatalog - the managed catalog of reasons
for internal stock consumption (Limpeza, Quebra/Perda...). Mirrors
resource_type_service.py's CRUD shape exactly, since both are consumed
through the same generic catalog UI in Categorias.jsx.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.consumption_reason_catalog import ConsumptionReasonCatalog


class ConsumptionReasonNotFoundError(Exception):
    pass


class ConsumptionReasonAlreadyExistsError(Exception):
    pass


async def create_consumption_reason(db: AsyncSession, company_id: uuid.UUID, name: str) -> ConsumptionReasonCatalog:
    existing_result = await db.execute(
        select(ConsumptionReasonCatalog).where(ConsumptionReasonCatalog.company_id == company_id, ConsumptionReasonCatalog.name == name)
    )
    if existing_result.scalar_one_or_none() is not None:
        raise ConsumptionReasonAlreadyExistsError(f"Ja existe um motivo chamado '{name}'")

    reason = ConsumptionReasonCatalog(company_id=company_id, name=name)
    db.add(reason)
    await db.commit()
    await db.refresh(reason)
    return reason


async def get_consumption_reason_or_raise(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID) -> ConsumptionReasonCatalog:
    result = await db.execute(
        select(ConsumptionReasonCatalog).where(ConsumptionReasonCatalog.id == reason_id, ConsumptionReasonCatalog.company_id == company_id)
    )
    reason = result.scalar_one_or_none()
    if reason is None:
        raise ConsumptionReasonNotFoundError("Motivo nao encontrado")
    return reason


async def list_consumption_reasons(db: AsyncSession, company_id: uuid.UUID) -> list[ConsumptionReasonCatalog]:
    result = await db.execute(select(ConsumptionReasonCatalog).where(ConsumptionReasonCatalog.company_id == company_id).order_by(ConsumptionReasonCatalog.name))
    return list(result.scalars().all())


async def update_consumption_reason(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID, name: str) -> ConsumptionReasonCatalog:
    reason = await get_consumption_reason_or_raise(db, company_id, reason_id)
    if name != reason.name:
        existing_result = await db.execute(
            select(ConsumptionReasonCatalog).where(ConsumptionReasonCatalog.company_id == company_id, ConsumptionReasonCatalog.name == name, ConsumptionReasonCatalog.id != reason_id)
        )
        if existing_result.scalar_one_or_none() is not None:
            raise ConsumptionReasonAlreadyExistsError(f"Ja existe um motivo chamado '{name}'")
    reason.name = name
    await db.commit()
    await db.refresh(reason)
    return reason


async def toggle_consumption_reason_status(db: AsyncSession, company_id: uuid.UUID, reason_id: uuid.UUID) -> ConsumptionReasonCatalog:
    reason = await get_consumption_reason_or_raise(db, company_id, reason_id)
    reason.is_active = not reason.is_active
    await db.commit()
    await db.refresh(reason)
    return reason
