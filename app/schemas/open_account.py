import uuid
from datetime import datetime

from pydantic import BaseModel, Field


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
    booking_id: uuid.UUID | None = None
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
    # None: the document type catalog decides (a type paid on issue - see default_paid_on_issue_type)
    invoice_type: str | None = None
    payments: list[OpenAccountClosePaymentInput] = []


class OpenAccountTransferItem(BaseModel):
    line_id: uuid.UUID
    quantity: float = Field(gt=0)


class OpenAccountTransferRequest(BaseModel):
    # Lines (or parts of lines) to move. Destination: an existing open account
    # (target_account_id) or a new one created on the fly - on target_resource_id
    # (another table; the label defaults to its name) or, without it, on the SAME
    # resource as the source under new_label (a split of the bill).
    items: list[OpenAccountTransferItem] = Field(min_length=1)
    target_account_id: uuid.UUID | None = None
    target_resource_id: uuid.UUID | None = None
    new_label: str | None = None


class OpenAccountTransferResponse(BaseModel):
    source_account: OpenAccountResponse
    target_account: OpenAccountResponse
    source_closed: bool
