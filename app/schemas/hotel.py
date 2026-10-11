import uuid
from datetime import datetime

from pydantic import BaseModel

from app.schemas.booking import BookingResponse
from app.schemas.open_account import OpenAccountResponse


class CheckInResponse(BaseModel):
    booking: BookingResponse
    account: OpenAccountResponse


class StayExtendRequest(BaseModel):
    """The new end of a stay in progress (later to stay longer, earlier to leave sooner)."""
    ends_at: datetime


class OccupancyHistoryEntry(BaseModel):
    booking_id: uuid.UUID
    resource_name: str
    customer_name: str | None
    starts_at: datetime
    ends_at: datetime
    status: str
    invoice_series: str | None
    invoice_number: int | None
    invoice_total: float | None
