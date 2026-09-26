"""
Business logic for the fiscal Year / Period hierarchy.
See specification v6/v7, section 3.4: strict two-level lock.

DECISION (business rule refinement): opening is strictly sequential, computed
by the system rather than freely chosen by the user:
- Years: cannot skip forward (must close the current year before opening the
  next one) and cannot go backward (never re-open an earlier year once the
  latest year has been opened). The system always proposes exactly one valid
  next year: today's calendar year if none exists yet, otherwise
  (latest year + 1) once the latest year is closed.
- Periods (months): within an open year, months open in calendar order
  (1..12), one at a time - the next open must be (last opened month + 1),
  or 1 if none exist yet. A month cannot open while another is still open.
"""
import uuid
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fiscal_year import FiscalYear
from app.models.fiscal_period import FiscalPeriod
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.cash_movement import CashMovement, CashMovementStatus


class FiscalYearAlreadyExistsError(Exception):
    pass


class FiscalYearNotFoundError(Exception):
    pass


class FiscalPeriodNotFoundError(Exception):
    pass


class InvalidFiscalOperationError(Exception):
    """Raised when a hierarchy or sequencing rule (section 3.4) would be violated."""
    pass


async def get_latest_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> FiscalYear | None:
    result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.year.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_next_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> int | None:
    """
    Returns the year that would be opened next, or None if a year is
    already open (must be closed first before proposing the next one).
    """
    latest = await get_latest_fiscal_year(db, company_id)
    if latest is None:
        return date.today().year
    if latest.is_open:
        return None
    return latest.year + 1


async def open_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> FiscalYear:
    """
    Opens the next valid fiscal year, computed by the system (section 3.4 +
    sequential rule). The caller cannot choose an arbitrary year.
    """
    next_year = await get_next_fiscal_year(db, company_id)
    if next_year is None:
        raise InvalidFiscalOperationError(
            "Ja existe um ano fiscal aberto - feche-o antes de abrir o proximo"
        )

    fiscal_year = FiscalYear(company_id=company_id, year=next_year, is_open=True)
    db.add(fiscal_year)
    await db.commit()
    await db.refresh(fiscal_year)
    return fiscal_year


async def list_fiscal_years(db: AsyncSession, company_id: uuid.UUID) -> list[FiscalYear]:
    result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.year.desc())
    )
    return list(result.scalars().all())


async def get_fiscal_year_or_raise(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalYear:
    result = await db.execute(
        select(FiscalYear).where(FiscalYear.id == fiscal_year_id, FiscalYear.company_id == company_id)
    )
    fiscal_year = result.scalar_one_or_none()
    if fiscal_year is None:
        raise FiscalYearNotFoundError("Ano fiscal nao encontrado")
    return fiscal_year


async def close_fiscal_year(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalYear:
    """Closes a fiscal year. Only allowed if no period under it is still open."""
    fiscal_year = await get_fiscal_year_or_raise(db, company_id, fiscal_year_id)

    open_periods = await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year_id, FiscalPeriod.is_open == True)
    )
    if open_periods.scalar_one_or_none() is not None:
        raise InvalidFiscalOperationError(
            "Nao e possivel fechar o ano enquanto existir um periodo (mes) aberto"
        )

    fiscal_year.is_open = False
    await db.commit()
    await db.refresh(fiscal_year)
    return fiscal_year


async def get_next_fiscal_month(db: AsyncSession, fiscal_year_id: uuid.UUID) -> int | None:
    """
    Returns the month (1-12) that would be opened next within this year,
    or None if a month is already open, or None if all 12 months are done.

    DECISION: the very first month opened for a fiscal year is the real
    current calendar month (date.today().month) when that year matches
    today's real year - not always January. This lets a company start
    using the system mid-year; earlier months simply stay "nao iniciado"
    forever (never opened). For any other fiscal year (opened later,
    necessarily a future year per the sequential rule), the first month
    is January as usual, since the whole year lies ahead.
    """
    year_result = await db.execute(select(FiscalYear).where(FiscalYear.id == fiscal_year_id))
    fiscal_year = year_result.scalar_one_or_none()

    result = await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year_id).order_by(FiscalPeriod.month.desc()).limit(1)
    )
    latest = result.scalar_one_or_none()

    if latest is None:
        if fiscal_year is not None and fiscal_year.year == date.today().year:
            return date.today().month
        return 1
    if latest.is_open:
        return None
    if latest.month >= 12:
        return None
    return latest.month + 1


async def open_fiscal_period(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalPeriod:
    """Opens the next valid month within the year, computed by the system."""
    fiscal_year = await get_fiscal_year_or_raise(db, company_id, fiscal_year_id)

    if not fiscal_year.is_open:
        raise InvalidFiscalOperationError("Nao e possivel abrir um periodo num ano fechado")

    next_month = await get_next_fiscal_month(db, fiscal_year_id)
    if next_month is None:
        raise InvalidFiscalOperationError(
            "Ja existe um periodo aberto neste ano, ou todos os meses ja foram concluidos"
        )

    period = FiscalPeriod(company_id=company_id, fiscal_year_id=fiscal_year_id, month=next_month, is_open=True)
    db.add(period)
    await db.commit()
    await db.refresh(period)
    return period


async def list_fiscal_periods(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> list[FiscalPeriod]:
    result = await db.execute(
        select(FiscalPeriod)
        .where(FiscalPeriod.company_id == company_id, FiscalPeriod.fiscal_year_id == fiscal_year_id)
        .order_by(FiscalPeriod.month)
    )
    return list(result.scalars().all())


async def close_fiscal_period(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> FiscalPeriod:
    result = await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.id == period_id, FiscalPeriod.company_id == company_id)
    )
    period = result.scalar_one_or_none()
    if period is None:
        raise FiscalPeriodNotFoundError("Periodo fiscal nao encontrado")

    # A period cannot close while cash is still "in flight" for this company - an open cash
    # session (drawer not yet counted/closed) or a transfer awaiting reception at its destination.
    open_sessions_count = (await db.execute(
        select(func.count(CashSession.id)).where(
            CashSession.company_id == company_id, CashSession.status == CashSessionStatus.ABERTA
        )
    )).scalar_one()
    if open_sessions_count > 0:
        raise InvalidFiscalOperationError(
            f"Nao e possivel fechar o periodo - existem {open_sessions_count} caixa(s) ainda aberta(s). "
            "Feche todas as sessoes de caixa antes de fechar o periodo."
        )

    pending_transfers_count = (await db.execute(
        select(func.count(CashMovement.id)).where(
            CashMovement.company_id == company_id, CashMovement.status == CashMovementStatus.PENDENTE
        )
    )).scalar_one()
    if pending_transfers_count > 0:
        raise InvalidFiscalOperationError(
            f"Nao e possivel fechar o periodo - existem {pending_transfers_count} transferencia(s) de caixa "
            "por receber. Confirme a rececao antes de fechar o periodo."
        )

    period.is_open = False
    await db.commit()
    await db.refresh(period)
    return period


MONTH_NAMES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


async def get_current_period_label(db: AsyncSession, company_id: uuid.UUID) -> str | None:
    """
    Returns a human-readable label for the currently open period, e.g.
    "Agosto 2026" - used in the navbar in place of user name/role. Returns
    None if no year or no period is currently open.
    """
    year_result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.is_open == True)
    )
    fiscal_year = year_result.scalar_one_or_none()
    if fiscal_year is None:
        return None

    period_result = await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year.id, FiscalPeriod.is_open == True)
    )
    period = period_result.scalar_one_or_none()
    if period is None:
        return None

    return f"{MONTH_NAMES_PT[period.month]} {fiscal_year.year}"


async def is_period_open_for_date(db: AsyncSession, company_id: uuid.UUID, check_date: date) -> bool:
    """
    Checks whether the Year AND Period covering check_date are both open.
    Used by any module creating dated transactional data (invoice, stock, etc.)
    """
    year_result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == check_date.year)
    )
    fiscal_year = year_result.scalar_one_or_none()
    if fiscal_year is None or not fiscal_year.is_open:
        return False

    period_result = await db.execute(
        select(FiscalPeriod).where(
            FiscalPeriod.fiscal_year_id == fiscal_year.id,
            FiscalPeriod.month == check_date.month,
        )
    )
    period = period_result.scalar_one_or_none()
    if period is None or not period.is_open:
        return False

    return True




class PeriodClosedError(Exception):
    """Raised when the fiscal Year/Period covering a given date is not open."""
    pass


async def ensure_period_open(db: AsyncSession, company_id: uuid.UUID, check_date: date) -> None:
    """Same check as is_period_open_for_date, but raises PeriodClosedError with a message that
    names precisely which one is missing/closed (year vs month) - avoids a generic message that
    sends the GESTOR looking in the wrong place (see the double-check-date confusion discussion)."""
    year_result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == check_date.year)
    )
    fiscal_year = year_result.scalar_one_or_none()
    if fiscal_year is None or not fiscal_year.is_open:
        raise PeriodClosedError(
            f"O ano fiscal {check_date.year} nao esta aberto. Contacte o GESTOR para o abrir antes de faturar."
        )

    period_result = await db.execute(
        select(FiscalPeriod).where(
            FiscalPeriod.fiscal_year_id == fiscal_year.id,
            FiscalPeriod.month == check_date.month,
        )
    )
    period = period_result.scalar_one_or_none()
    if period is None or not period.is_open:
        raise PeriodClosedError(
            f"O periodo de {MONTH_NAMES_PT[check_date.month]} de {check_date.year} nao esta aberto. "
            "Contacte o GESTOR para o abrir antes de faturar."
        )
