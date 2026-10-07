"""
Business logic for Establishment - company-scoped, needed for electronic
invoicing series requests (Video 8).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.establishment import Establishment


class EstablishmentNotFoundError(Exception):
    pass


async def list_establishments(db: AsyncSession, company_id: uuid.UUID) -> list[Establishment]:
    result = await db.execute(
        select(Establishment).where(Establishment.company_id == company_id).order_by(Establishment.name)
    )
    return list(result.scalars().all())


async def create_establishment(db: AsyncSession, company_id: uuid.UUID, code: str, name: str, description: str | None = None) -> Establishment:
    establishment = Establishment(company_id=company_id, code=code, name=name, description=description)
    db.add(establishment)
    await db.commit()
    await db.refresh(establishment)
    return establishment


async def update_establishment(db: AsyncSession, company_id: uuid.UUID, establishment_id: uuid.UUID, code: str, name: str, description: str | None = None) -> Establishment:
    result = await db.execute(select(Establishment).where(Establishment.id == establishment_id, Establishment.company_id == company_id))
    establishment = result.scalar_one_or_none()
    if establishment is None:
        raise EstablishmentNotFoundError("Estabelecimento nao encontrado")
    establishment.code = code
    establishment.name = name
    establishment.description = description
    await db.commit()
    await db.refresh(establishment)
    return establishment


async def toggle_establishment(db: AsyncSession, company_id: uuid.UUID, establishment_id: uuid.UUID) -> Establishment:
    result = await db.execute(select(Establishment).where(Establishment.id == establishment_id, Establishment.company_id == company_id))
    establishment = result.scalar_one_or_none()
    if establishment is None:
        raise EstablishmentNotFoundError("Estabelecimento nao encontrado")
    establishment.is_active = not establishment.is_active
    await db.commit()
    await db.refresh(establishment)
    return establishment
