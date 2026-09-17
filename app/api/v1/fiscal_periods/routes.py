"""
Fiscal Year/Period routes.
See specification v6/v7, section 6.2: opening/closing a Year or Period is
an exclusive power of the GESTOR - not ADMIN, not CAIXA.
Year/month values are computed server-side (strict sequential rule) -
the client never chooses them.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.models.user import User
from app.schemas.fiscal_period import (
    FiscalYearResponse,
    FiscalPeriodResponse,
    NextFiscalYearResponse,
    NextFiscalMonthResponse,
)
from app.services.fiscal_period_service import (
    open_fiscal_year,
    list_fiscal_years,
    close_fiscal_year,
    get_next_fiscal_year,
    open_fiscal_period,
    list_fiscal_periods,
    close_fiscal_period,
    get_next_fiscal_month,
    get_current_period_label,
    FiscalYearNotFoundError,
    FiscalPeriodNotFoundError,
    InvalidFiscalOperationError,
)

router = APIRouter(prefix="/api/v1/fiscal", tags=["fiscal"])


@router.get("/years/next", response_model=NextFiscalYearResponse)
async def get_next_year(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """What year would open next, or null if one is already open."""
    next_year = await get_next_fiscal_year(db, current_user.company_id)
    return NextFiscalYearResponse(next_year=next_year)


@router.post("/years", response_model=FiscalYearResponse, status_code=status.HTTP_201_CREATED)
async def create_fiscal_year(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await open_fiscal_year(db, current_user.company_id)
    except InvalidFiscalOperationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/years", response_model=list[FiscalYearResponse])
async def get_fiscal_years(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    return await list_fiscal_years(db, current_user.company_id)


@router.patch("/years/{fiscal_year_id}/close", response_model=FiscalYearResponse)
async def close_year(
    fiscal_year_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await close_fiscal_year(db, current_user.company_id, fiscal_year_id)
    except FiscalYearNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidFiscalOperationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/years/{fiscal_year_id}/periods/next", response_model=NextFiscalMonthResponse)
async def get_next_month(
    fiscal_year_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    """What month would open next within this year, or null if unavailable."""
    next_month = await get_next_fiscal_month(db, fiscal_year_id)
    return NextFiscalMonthResponse(next_month=next_month)


@router.post("/years/{fiscal_year_id}/periods", response_model=FiscalPeriodResponse, status_code=status.HTTP_201_CREATED)
async def create_fiscal_period(
    fiscal_year_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await open_fiscal_period(db, current_user.company_id, fiscal_year_id)
    except FiscalYearNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidFiscalOperationError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/years/{fiscal_year_id}/periods", response_model=list[FiscalPeriodResponse])
async def get_fiscal_periods(
    fiscal_year_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    return await list_fiscal_periods(db, current_user.company_id, fiscal_year_id)


@router.patch("/periods/{period_id}/close", response_model=FiscalPeriodResponse)
async def close_period(
    period_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    try:
        return await close_fiscal_period(db, current_user.company_id, period_id)
    except FiscalPeriodNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/current-period")
async def get_current_period(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR", "CAIXA", "ARMAZENISTA", "CONTABILISTA")),
):
    """
    Returns the currently open period label (e.g. "Agosto 2026") for the
    navbar - null if no year/period is currently open.
    """
    label = await get_current_period_label(db, current_user.company_id)
    return {"label": label}

