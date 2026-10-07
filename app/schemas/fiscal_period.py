"""
Pydantic schemas for the fiscal Year / Period hierarchy.
See specification v6/v7, section 3.4.
Year and month are NOT supplied by the client - they are computed
server-side following the strict sequential rule (see fiscal_period_service.py).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


class FiscalYearResponse(BaseModel):
    id: uuid.UUID
    year: int
    status: str  # ABERTO / FECHO_PARCIAL / FECHADO
    is_open: bool  # ABERTO (every operation)
    created_at: datetime

    class Config:
        from_attributes = True


class FiscalPeriodResponse(BaseModel):
    id: uuid.UUID
    fiscal_year_id: uuid.UUID
    month: int
    status: str  # ABERTO / FECHO_PARCIAL / FECHADO
    is_open: bool  # ABERTO (every operation)
    created_at: datetime

    class Config:
        from_attributes = True


class NextFiscalYearResponse(BaseModel):
    """What the system would open next, or null if a year is already open."""
    next_year: int | None


class NextFiscalMonthResponse(BaseModel):
    """What the system would open next within a year, or null if unavailable."""
    next_month: int | None
