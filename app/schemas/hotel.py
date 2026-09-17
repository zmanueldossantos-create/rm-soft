import uuid

from pydantic import BaseModel

from app.schemas.booking import BookingResponse
from app.schemas.open_account import OpenAccountResponse


class CheckInResponse(BaseModel):
    booking: BookingResponse
    account: OpenAccountResponse


class CheckOutPaymentInput(BaseModel):
    payment_method_id: uuid.UUID
    amount: float


from datetime import datetime


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


class CheckOutRequest(BaseModel):
    payments: list[CheckOutPaymentInput] = []
