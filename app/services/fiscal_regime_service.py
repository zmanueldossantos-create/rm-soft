"""
Business logic for fiscal regimes (SUPER_ADMIN only, platform-wide).
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fiscal_regime import FiscalRegime


class FiscalRegimeNotFoundError(Exception):
    pass


class FiscalRegimeInvalidError(Exception):
    """A regime whose settings contradict each other."""


def _check_required_exemption(allows_ise: bool, required_exemption_id) -> None:
    """A regime that imposes an exemption motive must allow exempt (ISE) rates - the motive goes on exempt lines only."""
    if required_exemption_id is not None and not allows_ise:
        raise FiscalRegimeInvalidError("Um regime com motivo de isencao obrigatorio tem de permitir a taxa ISE (isenta)")


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
    required_exemption_id: uuid.UUID | None = None,
) -> FiscalRegime:
    _check_required_exemption(allows_ise, required_exemption_id)
    regime = FiscalRegime(
        name=name,
        description=description,
        allows_nor=allows_nor,
        allows_red=allows_red,
        allows_ise=allows_ise,
        allows_int=allows_int,
        allows_out=allows_out,
        required_exemption_id=required_exemption_id,
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
    required_exemption_id: uuid.UUID | None = None,
) -> FiscalRegime:
    _check_required_exemption(allows_ise, required_exemption_id)
    regime = await get_fiscal_regime_or_raise(db, regime_id)
    regime.name = name
    regime.description = description
    regime.allows_nor = allows_nor
    regime.allows_red = allows_red
    regime.allows_ise = allows_ise
    regime.allows_int = allows_int
    regime.allows_out = allows_out
    regime.required_exemption_id = required_exemption_id
    # Its companies follow at once: rates of the categories it now allows or forbids.
    from app.services.company_service import propagate_regime_rates
    await propagate_regime_rates(db, regime.id)
    await db.commit()
    await db.refresh(regime)
    return regime


async def toggle_fiscal_regime_status(db: AsyncSession, regime_id: uuid.UUID) -> FiscalRegime:
    regime = await get_fiscal_regime_or_raise(db, regime_id)
    regime.is_active = not regime.is_active
    await db.commit()
    await db.refresh(regime)
    return regime
