"""Fiscal periods and years in three states: ABERTO, FECHO_PARCIAL (internal late entries only), FECHADO.
The tests build their own year (far in the future) so they never depend on today's date."""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.services.fiscal_period_service import (
    InvalidFiscalOperationError, PeriodClosedError, close_fiscal_period, close_fiscal_year, ensure_period_open,
    get_next_fiscal_year, open_fiscal_period, partial_close_fiscal_period, partial_close_fiscal_year,
)


async def _own_year(db, company_id, year=2090, months=()):
    """A year of our own with the given (month, status) periods - no dependency on today's date."""
    fiscal_year = FiscalYear(company_id=company_id, year=year, status="ABERTO")
    db.add(fiscal_year)
    await db.commit()
    await db.refresh(fiscal_year)
    periods = []
    for month, status in months:
        period = FiscalPeriod(company_id=company_id, fiscal_year_id=fiscal_year.id, month=month, status=status)
        db.add(period)
        periods.append(period)
    await db.commit()
    for period in periods:
        await db.refresh(period)
    return fiscal_year, periods


async def _close_fixture_periods(db, company_id):
    """The conftest opens today's year and month: close them so our own year is the only open one."""
    for period in (await db.execute(select(FiscalPeriod).where(FiscalPeriod.company_id == company_id))).scalars():
        period.status = "FECHADO"
    for year in (await db.execute(select(FiscalYear).where(FiscalYear.company_id == company_id))).scalars():
        year.status = "FECHADO"
    await db.commit()


@pytest.mark.asyncio
async def test_soft_close_then_the_next_month_opens(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    fiscal_year, (september,) = await _own_year(db, company_id, months=[(9, "ABERTO")])
    soft = await partial_close_fiscal_period(db, company_id, september.id)
    assert soft.status == "FECHO_PARCIAL"
    october = await open_fiscal_period(db, company_id, fiscal_year.id)
    assert (october.month, october.status) == (10, "ABERTO")


@pytest.mark.asyncio
async def test_a_soft_closed_month_refuses_automatic_operations(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    await _own_year(db, company_id, months=[(9, "FECHO_PARCIAL"), (10, "ABERTO")])
    with pytest.raises(PeriodClosedError, match="fechado parcialmente"):
        await ensure_period_open(db, company_id, date(2090, 9, 30))
    await ensure_period_open(db, company_id, date(2090, 10, 1))  # the active month accepts everything


@pytest.mark.asyncio
async def test_only_one_soft_closed_period_at_a_time(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    _, (september, october) = await _own_year(db, company_id, months=[(9, "FECHO_PARCIAL"), (10, "ABERTO")])
    with pytest.raises(InvalidFiscalOperationError, match="ainda esta fechado parcialmente"):
        await partial_close_fiscal_period(db, company_id, october.id)
    closed = await close_fiscal_period(db, company_id, september.id)
    assert closed.status == "FECHADO"
    assert (await partial_close_fiscal_period(db, company_id, october.id)).status == "FECHO_PARCIAL"


@pytest.mark.asyncio
async def test_year_soft_close_opens_the_way_to_the_next_year(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    fiscal_year, (december,) = await _own_year(db, company_id, months=[(12, "ABERTO")])
    with pytest.raises(InvalidFiscalOperationError, match="antes de fechar parcialmente o ano"):
        await partial_close_fiscal_year(db, company_id, fiscal_year.id)
    await partial_close_fiscal_period(db, company_id, december.id)
    assert (await partial_close_fiscal_year(db, company_id, fiscal_year.id)).status == "FECHO_PARCIAL"
    assert await get_next_fiscal_year(db, company_id) == 2091


@pytest.mark.asyncio
async def test_a_year_closes_for_good_only_when_every_month_is_closed(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    fiscal_year, (november, december) = await _own_year(db, company_id, months=[(11, "FECHADO"), (12, "FECHO_PARCIAL")])
    with pytest.raises(InvalidFiscalOperationError, match="ou fechado parcialmente"):
        await close_fiscal_year(db, company_id, fiscal_year.id)
    await close_fiscal_period(db, company_id, december.id)
    assert (await close_fiscal_year(db, company_id, fiscal_year.id)).status == "FECHADO"


@pytest.mark.asyncio
async def test_a_year_is_never_soft_closed_mid_year(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    await _close_fixture_periods(db, company_id)
    fiscal_year, _ = await _own_year(db, company_id, months=[(9, "FECHO_PARCIAL")])
    with pytest.raises(InvalidFiscalOperationError, match="depois de Dezembro"):
        await partial_close_fiscal_year(db, company_id, fiscal_year.id)
