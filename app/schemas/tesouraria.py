"""
Pydantic schemas for the Tesouraria module - CashMovementReason, CashMovement,
and user <-> POS cash-point associations.
"""
import uuid
from typing import Literal
from datetime import date, datetime

from pydantic import BaseModel, field_validator

from app.schemas.moedeiro import DenominationCountLineInput


class CashMovementReasonCreateRequest(BaseModel):
    name: str
    direction: Literal["ENTRADA", "SAIDA"]


class CashMovementReasonResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    direction: str
    is_active: bool

    class Config:
        from_attributes = True


class CashMovementCreateRequest(BaseModel):
    movement_type: Literal["TRANSFERENCIA", "ENTRADA_EXTERNA", "SAIDA_EXTERNA"]
    amount: float
    source_pos_id: uuid.UUID | None = None
    destination_pos_id: uuid.UUID | None = None
    reason_id: uuid.UUID | None = None
    movement_date: date | None = None
    description: str | None = None
    # the notes and coins sent - a transfer from a till with billetage only
    denomination_lines: list[DenominationCountLineInput] | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("O valor deve ser maior que zero")
        return v


class CashMovementReceiveRequest(BaseModel):
    """The notes and coins received - a receiving till with billetage only."""
    denomination_lines: list[DenominationCountLineInput] = []


class TransferBilletageLine(BaseModel):
    denomination_id: uuid.UUID
    value: float
    type: str
    quantity: int
    amount: float


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


# ---------- Tesouraria overview (the manager's view of every till) ----------

class TreasuryTill(BaseModel):
    pos_id: uuid.UUID
    pos_name: str
    activity_name: str
    is_default: bool
    billetage_enabled: bool
    is_open: bool
    session_id: uuid.UUID | None
    business_date: date | None
    opened_at: datetime | None
    opened_by: str | None
    last_closed_at: datetime | None
    cash: float
    pending_out: float
    pending_in: float


class TreasuryTotals(BaseModel):
    cash: float
    in_transit: float
    open_tills: int
    tills: int


class TreasuryPositionResponse(BaseModel):
    tills: list[TreasuryTill]
    totals: TreasuryTotals


class TreasuryTillRef(BaseModel):
    id: uuid.UUID
    name: str
    activity_name: str


class TreasuryMovement(BaseModel):
    id: uuid.UUID
    movement_type: str
    status: str
    movement_date: date
    created_at: datetime
    amount: float
    source: TreasuryTillRef | None
    destination: TreasuryTillRef | None
    reason: str | None
    description: str | None
    created_by: str | None
    received_by: str | None
    received_at: datetime | None


class TreasuryClosing(BaseModel):
    session_id: uuid.UUID
    pos_id: uuid.UUID
    pos_name: str
    activity_name: str
    business_date: date
    opened_at: datetime
    opened_by: str | None
    closed_at: datetime | None
    closed_by: str | None
    opening_amount: float | None
    expected: float | None
    counted: float | None
    difference: float | None
    notes: str | None
