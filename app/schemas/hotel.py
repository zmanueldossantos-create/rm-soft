import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.booking import BookingResponse
from app.schemas.open_account import OpenAccountResponse


class CheckInResponse(BaseModel):
    booking: BookingResponse
    account: OpenAccountResponse


class WalkInPaymentInput(BaseModel):
    payment_method_id: uuid.UUID
    amount: float


class WalkInRequest(BaseModel):
    """A prepaid passage: the room, the timed service, the till that cashes it and the payments."""
    resource_id: uuid.UUID
    service_id: uuid.UUID
    pos_id: uuid.UUID
    payments: list[WalkInPaymentInput]
    customer_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=150)
    party_size: int | None = Field(default=None, ge=1, le=1000)
    terminal_id: uuid.UUID | None = None  # the TPA / Express of the bank payments (Tesouraria): None = decided by itself


class WalkInResponse(BaseModel):
    booking: BookingResponse
    invoice_id: uuid.UUID


class StayExtendRequest(BaseModel):
    """The new end of a stay in progress (later to stay longer, earlier to leave sooner). A passage (paid at its
    Entrada) pays its extra time at once: the till, the payments and the terminal, as at its Entrada."""
    ends_at: datetime
    pos_id: uuid.UUID | None = None
    payments: list[WalkInPaymentInput] = []
    terminal_id: uuid.UUID | None = None


class CheckOutRequest(BaseModel):
    """The exit. A passage past its paid time: its excess charged (pos_id, payments, terminal_id) or let go with the
    reason said (waive_reason). Nothing for any other exit."""
    pos_id: uuid.UUID | None = None
    payments: list[WalkInPaymentInput] = []
    terminal_id: uuid.UUID | None = None
    waive_reason: str | None = Field(default=None, max_length=255)


class OverstayResponse(BaseModel):
    """How long a passage has stayed past its paid end, and the slices of its rate that starts."""
    minutes: int
    slices: int
