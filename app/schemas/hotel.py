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


class WalkInResponse(BaseModel):
    booking: BookingResponse
    invoice_id: uuid.UUID


class StayExtendRequest(BaseModel):
    """The new end of a stay in progress (later to stay longer, earlier to leave sooner)."""
    ends_at: datetime


class OccupancyHistoryEntry(BaseModel):
    booking_id: uuid.UUID
    resource_name: str
    customer_name: str | None
    guest_name: str | None = None
    starts_at: datetime
    ends_at: datetime
    checked_out_at: datetime | None = None
    overstay_minutes: int = 0
    status: str
    invoice_series: str | None
    invoice_number: int | None
    invoice_total: float | None
