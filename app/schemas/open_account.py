import uuid
from datetime import datetime

from pydantic import BaseModel


class OpenAccountCreateRequest(BaseModel):
    activity_id: uuid.UUID
    pos_id: uuid.UUID
    label: str
    resource_id: uuid.UUID | None = None
    customer_id: uuid.UUID | None = None
    notes: str | None = None


class OpenAccountResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    activity_id: uuid.UUID
    pos_id: uuid.UUID
    resource_id: uuid.UUID | None
    customer_id: uuid.UUID | None
    label: str
    notes: str | None
    status: str
    opened_by_user_id: uuid.UUID
    opened_at: datetime
    closed_at: datetime | None
    invoice_id: uuid.UUID | None

    class Config:
        from_attributes = True


class OpenAccountLineCreateRequest(BaseModel):
    product_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    quantity: float = 1


class OpenAccountLineUpdateRequest(BaseModel):
    quantity: float


class OpenAccountLineResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    product_id: uuid.UUID | None
    service_id: uuid.UUID | None
    name_snapshot: str
    quantity: float
    unit_price: float
    added_by_user_id: uuid.UUID
    added_at: datetime

    class Config:
        from_attributes = True


class OpenAccountClosePaymentInput(BaseModel):
    payment_method_id: uuid.UUID
    amount: float


class OpenAccountCloseRequest(BaseModel):
    invoice_type: str = "FACTURA_RECIBO"
    payments: list[OpenAccountClosePaymentInput] = []
