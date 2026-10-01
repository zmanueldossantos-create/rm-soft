"""
Business logic for the fiscal Year / Period hierarchy (specification v6/v7, section 3.4).

Three states, for years and periods alike (FiscalStatus):
- ABERTO: the active one - every operation, automatic ones included (sales, invoices, cash sessions).
- FECHO_PARCIAL: soft-closed - automatic / fiscal operations are refused (they need the active period), but internal
  manual entries (reception, transfer, loss, adjustment, production, internal consumption) may still be posted to it:
  a late entry belonging to the previous month, saved with its real date. At most ONE period and ONE year at a time.
- FECHADO: final, never reopened.

Opening stays strictly sequential and computed by the system (never chosen by the user):
- Years: the next year opens once the latest one is no longer ABERTO (soft- or finally closed); never backwards.
- Periods: months open in calendar order, one ABERTO at a time; the next one opens once the current one is no longer
  ABERTO. The first month of the current calendar year is today's month (a company can start mid-year).
"""
import uuid
from datetime import date

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.fiscal_year import FiscalYear
from app.models.fiscal_period import FiscalPeriod, FiscalStatus
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.cash_movement import CashMovement, CashMovementStatus

ABERTO, FECHO_PARCIAL, FECHADO = FiscalStatus.ABERTO.value, FiscalStatus.FECHO_PARCIAL.value, FiscalStatus.FECHADO.value

MONTH_NAMES_PT = [
    "", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
]


class FiscalYearAlreadyExistsError(Exception):
    pass


class FiscalYearNotFoundError(Exception):
    pass


class FiscalPeriodNotFoundError(Exception):
    pass


class InvalidFiscalOperationError(Exception):
    """Raised when a hierarchy or sequencing rule (section 3.4) would be violated."""
    pass


class PeriodClosedError(Exception):
    """Raised when the fiscal Year/Period covering a given date does not accept the operation."""
    pass


# ---------- Years

async def get_latest_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> FiscalYear | None:
    result = await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id).order_by(FiscalYear.year.desc()).limit(1)
    )
    return result.scalar_one_or_none()


async def get_next_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> int | None:
    """The year that would open next, or None while the latest one is still ABERTO."""
    latest = await get_latest_fiscal_year(db, company_id)
    if latest is None:
        return date.today().year
    if latest.status == ABERTO:
        return None
    return latest.year + 1


async def open_fiscal_year(db: AsyncSession, company_id: uuid.UUID) -> FiscalYear:
    """Opens the next valid fiscal year, computed by the system - the caller never chooses it."""
    next_year = await get_next_fiscal_year(db, company_id)
    if next_year is None:
        raise InvalidFiscalOperationError(
            "Ja existe um ano fiscal aberto - feche-o (parcial ou definitivamente) antes de abrir o proximo"
        )
    fiscal_year = FiscalYear(company_id=company_id, year=next_year, status=ABERTO)
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


async def partial_close_fiscal_year(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalYear:
    """Soft-closes a year (December soft-closed, the next year about to open): no month of it may still be ABERTO,
    and no other year may already be soft-closed."""
    fiscal_year = await get_fiscal_year_or_raise(db, company_id, fiscal_year_id)
    if fiscal_year.status != ABERTO:
        raise InvalidFiscalOperationError("So um ano aberto pode ser fechado parcialmente")
    open_period = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year_id, FiscalPeriod.status == ABERTO)
    )).scalar_one_or_none()
    if open_period is not None:
        raise InvalidFiscalOperationError(
            f"Feche (parcial ou definitivamente) o periodo de {MONTH_NAMES_PT[open_period.month]} "
            "antes de fechar parcialmente o ano"
        )
    # A year is soft-closed only to move on to the next one: after December, never mid-year.
    december = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year_id, FiscalPeriod.month == 12)
    )).scalar_one_or_none()
    if december is None:
        raise InvalidFiscalOperationError(
            "So e possivel fechar parcialmente o ano depois de Dezembro - feche parcialmente Dezembro primeiro"
        )
    other = (await db.execute(
        select(FiscalYear).where(
            FiscalYear.company_id == company_id, FiscalYear.status == FECHO_PARCIAL, FiscalYear.id != fiscal_year_id,
        )
    )).scalar_one_or_none()
    if other is not None:
        raise InvalidFiscalOperationError(
            f"O ano {other.year} ainda esta fechado parcialmente - feche-o definitivamente primeiro"
        )
    fiscal_year.status = FECHO_PARCIAL
    await db.commit()
    await db.refresh(fiscal_year)
    return fiscal_year


async def close_fiscal_year(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalYear:
    """Closes a fiscal year for good: every one of its months must be FECHADO."""
    fiscal_year = await get_fiscal_year_or_raise(db, company_id, fiscal_year_id)
    if fiscal_year.status == FECHADO:
        raise InvalidFiscalOperationError("O ano fiscal ja esta fechado")
    not_closed = (await db.execute(
        select(func.count(FiscalPeriod.id)).where(
            FiscalPeriod.fiscal_year_id == fiscal_year_id, FiscalPeriod.status != FECHADO,
        )
    )).scalar_one()
    if not_closed > 0:
        raise InvalidFiscalOperationError(
            "Nao e possivel fechar o ano enquanto existir um periodo (mes) aberto ou fechado parcialmente"
        )
    fiscal_year.status = FECHADO
    await db.commit()
    await db.refresh(fiscal_year)
    return fiscal_year


# ---------- Periods

async def get_next_fiscal_month(db: AsyncSession, fiscal_year_id: uuid.UUID) -> int | None:
    """
    The month (1-12) that would open next within this year, or None while a month is ABERTO, or once all 12 are done.
    The very first month opened for the current calendar year is today's month (a company can start mid-year); for any
    other year it is January.
    """
    fiscal_year = (await db.execute(select(FiscalYear).where(FiscalYear.id == fiscal_year_id))).scalar_one_or_none()
    latest = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year_id).order_by(FiscalPeriod.month.desc()).limit(1)
    )).scalar_one_or_none()
    if latest is None:
        if fiscal_year is not None and fiscal_year.year == date.today().year:
            return date.today().month
        return 1
    if latest.status == ABERTO:
        return None
    if latest.month >= 12:
        return None
    return latest.month + 1


async def open_fiscal_period(db: AsyncSession, company_id: uuid.UUID, fiscal_year_id: uuid.UUID) -> FiscalPeriod:
    """Opens the next valid month within the year, computed by the system."""
    fiscal_year = await get_fiscal_year_or_raise(db, company_id, fiscal_year_id)
    if fiscal_year.status != ABERTO:
        raise InvalidFiscalOperationError("Nao e possivel abrir um periodo num ano que nao esta aberto")
    next_month = await get_next_fiscal_month(db, fiscal_year_id)
    if next_month is None:
        raise InvalidFiscalOperationError(
            "Ja existe um periodo aberto neste ano, ou todos os meses ja foram concluidos"
        )
    period = FiscalPeriod(company_id=company_id, fiscal_year_id=fiscal_year_id, month=next_month, status=ABERTO)
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


async def _period_or_raise(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> FiscalPeriod:
    period = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.id == period_id, FiscalPeriod.company_id == company_id)
    )).scalar_one_or_none()
    if period is None:
        raise FiscalPeriodNotFoundError("Periodo fiscal nao encontrado")
    return period


async def _ensure_no_cash_in_flight(db: AsyncSession, company_id: uuid.UUID) -> None:
    """Automatic operations stop when a period leaves ABERTO: no cash may still be "in flight" - an open cash session
    (drawer not yet counted / closed) or a transfer awaiting reception at its destination."""
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


async def partial_close_fiscal_period(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> FiscalPeriod:
    """Soft-closes the ABERTO period: automatic operations stop there, internal late entries may still be posted to it.
    Only one period may be soft-closed at a time - the previous one must be closed for good first."""
    period = await _period_or_raise(db, company_id, period_id)
    if period.status != ABERTO:
        raise InvalidFiscalOperationError("So o periodo aberto pode ser fechado parcialmente")
    other = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.company_id == company_id, FiscalPeriod.status == FECHO_PARCIAL, FiscalPeriod.id != period_id,
        )
    )).first()
    if other is not None:
        other_period, other_year = other
        raise InvalidFiscalOperationError(
            f"O periodo de {MONTH_NAMES_PT[other_period.month]} de {other_year} ainda esta fechado parcialmente - "
            "feche-o definitivamente antes"
        )
    await _ensure_no_cash_in_flight(db, company_id)
    period.status = FECHO_PARCIAL
    await db.commit()
    await db.refresh(period)
    return period


async def close_fiscal_period(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> FiscalPeriod:
    """Closes a period for good (from ABERTO or FECHO_PARCIAL) - never reopened."""
    period = await _period_or_raise(db, company_id, period_id)
    if period.status == FECHADO:
        raise InvalidFiscalOperationError("O periodo ja esta fechado")
    if period.status == ABERTO:
        await _ensure_no_cash_in_flight(db, company_id)
    period.status = FECHADO
    await db.commit()
    await db.refresh(period)
    return period


# ---------- What is open now

async def _period_with_status(db: AsyncSession, company_id: uuid.UUID, status: str) -> tuple[FiscalPeriod, int] | None:
    row = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.company_id == company_id, FiscalPeriod.status == status,
        )
    )).first()
    return (row[0], row[1]) if row else None


async def get_period_overview(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The active period (every operation) and the soft-closed one (internal late entries only), for the navbar."""
    active = await _period_with_status(db, company_id, ABERTO)
    partial = await _period_with_status(db, company_id, FECHO_PARCIAL)
    return {
        "label": f"{MONTH_NAMES_PT[active[0].month]} {active[1]}" if active else None,
        "partial_label": f"{MONTH_NAMES_PT[partial[0].month]} {partial[1]}" if partial else None,
    }


async def get_current_period_label(db: AsyncSession, company_id: uuid.UUID) -> str | None:
    """The active period as a label ("Outubro 2026"), or None."""
    return (await get_period_overview(db, company_id))["label"]


async def is_period_open_for_date(db: AsyncSession, company_id: uuid.UUID, check_date: date) -> bool:
    """Whether the Year AND the Period covering check_date are both ABERTO (every operation allowed)."""
    fiscal_year = (await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == check_date.year)
    )).scalar_one_or_none()
    if fiscal_year is None or fiscal_year.status != ABERTO:
        return False
    period = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year.id, FiscalPeriod.month == check_date.month)
    )).scalar_one_or_none()
    return period is not None and period.status == ABERTO


async def ensure_period_open(db: AsyncSession, company_id: uuid.UUID, check_date: date) -> None:
    """The check of AUTOMATIC / fiscal operations (sales, invoices, cash sessions): the Year and the Period covering
    check_date must be ABERTO. Raises PeriodClosedError naming precisely what is wrong and where to go instead."""
    fiscal_year = (await db.execute(
        select(FiscalYear).where(FiscalYear.company_id == company_id, FiscalYear.year == check_date.year)
    )).scalar_one_or_none()
    active = await _period_with_status(db, company_id, ABERTO)
    active_hint = (f" O periodo aberto de momento e {MONTH_NAMES_PT[active[0].month]} de {active[1]} - "
                   "verifique a data do documento.") if active else ""
    if fiscal_year is None or fiscal_year.status != ABERTO:
        state = "esta fechado parcialmente" if fiscal_year is not None and fiscal_year.status == FECHO_PARCIAL else "nao esta aberto"
        raise PeriodClosedError(
            f"O ano fiscal {check_date.year} {state}. Contacte o GESTOR para o abrir antes de continuar.{active_hint}"
        )
    period = (await db.execute(
        select(FiscalPeriod).where(FiscalPeriod.fiscal_year_id == fiscal_year.id, FiscalPeriod.month == check_date.month)
    )).scalar_one_or_none()
    if period is not None and period.status == ABERTO:
        return
    label = f"{MONTH_NAMES_PT[check_date.month]} de {check_date.year}"
    if period is not None and period.status == FECHO_PARCIAL:
        raise PeriodClosedError(
            f"O periodo de {label} esta fechado parcialmente: so aceita lancamentos internos "
            f"(entradas de stock, transferencias, perdas, ajustes).{active_hint}"
        )
    if active is not None:
        hint = active_hint.strip()
    else:
        next_month = await get_next_fiscal_month(db, fiscal_year.id)
        hint = (f"Contacte o GESTOR para abrir o periodo de {MONTH_NAMES_PT[next_month]} de {fiscal_year.year} antes de continuar."
                if next_month is not None else "Contacte o GESTOR para abrir o periodo antes de continuar.")
    raise PeriodClosedError(f"O periodo de {label} nao esta aberto. {hint}")



async def resolve_posting_period(db: AsyncSession, company_id: uuid.UUID, fiscal_period_id: uuid.UUID | None = None) -> FiscalPeriod:
    """
    THE period of an INTERNAL entry (reception, transfer, loss, adjustment, production, internal consumption): the one
    given when it is ABERTO or FECHO_PARCIAL (a late entry belonging to the soft-closed month), otherwise the active
    one. The entry keeps its real date; it is booked in this period. A FECHADO period never takes anything.
    Sales and credit-note returns use the active period too (they already went through ensure_period_open).
    """
    if fiscal_period_id is None:
        active = await _period_with_status(db, company_id, ABERTO)
        if active is None:
            raise PeriodClosedError("Nao existe nenhum periodo aberto. Contacte o GESTOR para abrir o periodo.")
        return active[0]
    row = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.id == fiscal_period_id, FiscalPeriod.company_id == company_id,
        )
    )).first()
    if row is None:
        raise PeriodClosedError("Periodo fiscal invalido")
    period, year = row
    if period.status == FECHADO:
        raise PeriodClosedError(f"O periodo de {MONTH_NAMES_PT[period.month]} de {year} esta fechado definitivamente")
    return period


async def list_posting_periods(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """The periods an internal entry may be booked in: the active one and the soft-closed one, oldest first."""
    rows = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.company_id == company_id, FiscalPeriod.status.in_([ABERTO, FECHO_PARCIAL]),
        ).order_by(FiscalYear.year, FiscalPeriod.month)
    )).all()
    return [
        {"id": period.id, "label": f"{MONTH_NAMES_PT[period.month]} {year}", "status": period.status,
         "year": year, "month": period.month}
        for period, year in rows
    ]
