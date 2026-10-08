"""
Pydantic schemas for the Tesouraria module - CashMovementReason, CashMovement,
and user <-> POS cash-point associations.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class CashMovementReasonCreateRequest(BaseModel):
    name: str
    direction: str  # "ENTRADA" or "SAIDA"


class CashMovementReasonResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    direction: str
    is_active: bool

    class Config:
        from_attributes = True


class CashMovementCreateRequest(BaseModel):
    movement_type: str  # "TRANSFERENCIA" | "ENTRADA_EXTERNA" | "SAIDA_EXTERNA"
    amount: float
    source_pos_id: uuid.UUID | None = None
    destination_pos_id: uuid.UUID | None = None
    reason_id: uuid.UUID | None = None
    movement_date: date | None = None
    description: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("O valor deve ser maior que zero")
        return v


class CashMovementResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    movement_type: str
    source_pos_id: uuid.UUID | None
    destination_pos_id: uuid.UUID | None
    reason_id: uuid.UUID | None
    amount: float
    movement_date: date
    description: str | None
    created_by_user_id: uuid.UUID
    created_at: datetime
    status: str
    received_at: datetime | None
    received_by_user_id: uuid.UUID | None

    class Config:
        from_attributes = True


class AssignCashPointRequest(BaseModel):
    pos_id: uuid.UUID


class UserCashPointAccessResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    user_id: uuid.UUID
    pos_id: uuid.UUID

    class Config:
        from_attributes = True


class DailyReportEntry(BaseModel):
    type: str
    time: datetime
    business_date: date
    description: str
    amount: float
    direction: str
    reference: str
    payment_method: str | None = None
    is_cash: bool | None = None
