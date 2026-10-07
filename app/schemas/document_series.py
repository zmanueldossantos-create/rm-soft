"""Pydantic schemas for DocumentSeries (Video 4/8)."""
import uuid
from datetime import date, datetime
from pydantic import BaseModel


class DocumentSeriesCreateRequest(BaseModel):
    document_type_id: uuid.UUID | None = None  # None = "Todos" (MANUAL mode only)
    year: int | None = None
    establishment_id: uuid.UUID | None = None
    series_code: str | None = None  # required only in MANUAL mode with auto_series_year off
    description: str | None = None
    contingency_indicator: str | None = None
    is_predefined: bool = True
    # Only meaningful when document_type_id is None - which areas' document types to include.
    todos_facturacao: bool = False
    todos_tesouraria: bool = False
    todos_compras: bool = False


class DocumentSeriesUpdateRequest(BaseModel):
    description: str | None = None
    contingency_indicator: str | None = None
    is_predefined: bool | None = None


class DocumentSeriesResponse(BaseModel):
    id: uuid.UUID
    establishment_id: uuid.UUID | None
    document_type_id: uuid.UUID
    year: int
    issuance_mode: str
    series_code: str
    description: str | None
    number_start: int
    number_end: int
    date_start: date
    date_end: date
    contingency_indicator: str | None
    is_predefined: bool
    is_facturacao: bool
    is_tesouraria: bool
    is_compras: bool
    current_number: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True