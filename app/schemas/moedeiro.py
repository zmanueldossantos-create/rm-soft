"""
Pydantic schemas for the Moedeiro (billetage) feature - denominations and
cash-drawer counts.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


class DenominationResponse(BaseModel):
    id: uuid.UUID
    currency_id: uuid.UUID
    value: float
    denomination_type: str
    is_active: bool

    class Config:
        from_attributes = True


class DenominationCountLineInput(BaseModel):
    denomination_id: uuid.UUID
    quantity: int


class RecordDenominationCountRequest(BaseModel):
    cash_session_id: uuid.UUID
    count_type: str  # "ABERTURA" | "FECHO" | "TROCA_SAIDA" | "TROCA_ENTRADA"
    lines: list[DenominationCountLineInput]


class DenominationCountLineResponse(BaseModel):
    denomination_id: uuid.UUID
    quantity: int

    class Config:
        from_attributes = True


class DenominationCountResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    cash_session_id: uuid.UUID
    count_type: str
    counted_by_user_id: uuid.UUID
    counted_at: datetime
    total: float
    lines: list[DenominationCountLineResponse]
