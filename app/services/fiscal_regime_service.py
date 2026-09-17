"""
Business logic for fiscal regimes (SUPER_ADMIN only, platform-wide).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fiscal_regime import FiscalRegime


class FiscalRegimeNotFoundError(Exception):
    pass


async def list_fiscal_regimes(db: AsyncSession) -> list[FiscalRegime]:
    result = await db.execute(select(FiscalRegime).order_by(FiscalRegime.name))
    return list(result.scalars().all())


async def create_fiscal_regime(
    db: AsyncSession,
    name: str,
    description: str | None,
    allows_nor: bool,
    allows_red: bool,
    allows_ise: bool,
    allows_int: bool,
    allows_out: bool,
) -> FiscalRegime:
    regime = FiscalRegime(
        name=name,
        description=description,
        allows_nor=allows_nor,
        allows_red=allows_red,
        allows_ise=allows_ise,
        allows_int=allows_int,
        allows_out=allows_out,
    )
    db.add(regime)
    await db.commit()
    await db.refresh(regime)
    return regime


async def get_fiscal_regime_or_raise(db: AsyncSession, regime_id: uuid.UUID) -> FiscalRegime:
    result = await db.execute(select(FiscalRegime).where(FiscalRegime.id == regime_id))
    regime = result.scalar_one_or_none()
    if regime is None:
        raise FiscalRegimeNotFoundError("Regime fiscal nao encontrado")
    return regime


async def update_fiscal_regime(
    db: AsyncSession,
    regime_id: uuid.UUID,
    name: str,
    description: str | None,
    allows_nor: bool,
    allows_red: bool,
    allows_ise: bool,
    allows_int: bool,
    allows_out: bool,
) -> FiscalRegime:
    regime = await get_fiscal_regime_or_raise(db, regime_id)
    regime.name = name
    regime.description = description
    regime.allows_nor = allows_nor
    regime.allows_red = allows_red
    regime.allows_ise = allows_ise
    regime.allows_int = allows_int
    regime.allows_out = allows_out
    await db.commit()
    await db.refresh(regime)
    return regime


async def toggle_fiscal_regime_status(db: AsyncSession, regime_id: uuid.UUID) -> FiscalRegime:
    regime = await get_fiscal_regime_or_raise(db, regime_id)
    regime.is_active = not regime.is_active
    await db.commit()
    await db.refresh(regime)
    return regime
