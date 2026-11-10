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
    for_cash: bool = True   # used by the tills' entradas / saídas
    for_bank: bool = False  # used by the bank accounts' own movements


class CashMovementReasonResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    direction: str
    for_cash: bool
    for_bank: bool
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
    # a deposit (SAIDA_EXTERNA) or a withdrawal (ENTRADA_EXTERNA) with this bank account of the company
    bank_account_id: uuid.UUID | None = None

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
    bank_account_id: uuid.UUID | None = None
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


# ---------- Bancos: each bank account's balance and statement (bank_treasury_service) ----------

class BankPosition(BaseModel):
    id: uuid.UUID
    bank: str
    bank_name: str
    account_number: str
    iban: str
    currency: str
    is_active: bool
    opening_balance: float
    opening_date: date | None
    balance: float
    movements: int
    in_transit_in: float = 0  # transfers on their way to this account (em trânsito)
    opening_from_accounting: bool = False  # the opening balance set by the accounting's imported saldos iniciais


class BankStatementLine(BaseModel):
    date: date
    document: str
    description: str
    amount_in: float
    amount_out: float
    balance: float
    movement_id: uuid.UUID | None = None  # a typed movement still registered: «Anular»
    transfer_id: uuid.UUID | None = None  # a transfer not cancelled: «Anular»
    in_transit: bool = False  # a transfer out, not yet on the other account


class BankStatementAccount(BaseModel):
    id: uuid.UUID
    bank: str
    bank_name: str
    account_number: str
    iban: str
    currency: str
    is_active: bool
    opening_balance: float
    opening_date: date | None


class BankStatement(BaseModel):
    account: BankStatementAccount
    opening: float
    total_in: float
    total_out: float
    closing: float
    lines: list[BankStatementLine]


class BankOpeningBalanceRequest(BaseModel):
    amount: float
    opening_date: date


class BankMovementCreateRequest(BaseModel):
    reason_id: uuid.UUID
    amount: float
    movement_date: date
    reference: str | None = None
    description: str | None = None


class BankMovementCancelRequest(BaseModel):
    reason: str


class BankMovementResponse(BaseModel):
    id: uuid.UUID
    bank_account_id: uuid.UUID
    series: str
    number: int
    direction: str
    movement_date: date
    amount: float
    status: str

    class Config:
        from_attributes = True


# ---------- Terminais: TPA / Multicaixa Express and the bank account their payments land on ----------

class PaymentTerminalRequest(BaseModel):
    name: str
    kind: Literal["TPA", "EXPRESS"]
    bank_account_id: uuid.UUID
    pos_id: uuid.UUID | None = None  # None: any point of sale
    payment_method_ids: list[uuid.UUID]


class PaymentTerminalResponse(BaseModel):
    id: uuid.UUID
    name: str
    kind: str
    bank_account_id: uuid.UUID
    bank_account_label: str
    pos_id: uuid.UUID | None
    pos_name: str | None
    payment_method_ids: list[uuid.UUID]
    is_active: bool


# ---------- Transferências entre contas bancárias da empresa ----------

class BankTransferCreateRequest(BaseModel):
    to_account_id: uuid.UUID
    amount: float
    transfer_date: date
    reference: str | None = None
    description: str | None = None


class BankTransferConfirmRequest(BaseModel):
    available_date: date


class BankTransferResponse(BaseModel):
    id: uuid.UUID
    document: str
    from_account_id: uuid.UUID
    from_label: str
    to_account_id: uuid.UUID
    to_label: str
    amount: float
    transfer_date: date
    available_date: date | None
    status: str
    reference: str | None
    description: str | None
