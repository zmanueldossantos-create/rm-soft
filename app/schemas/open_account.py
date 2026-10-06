import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class OpenAccountCreateRequest(BaseModel):
    activity_id: uuid.UUID
    pos_id: uuid.UUID | None = None  # never chosen on screen: the activity's default till is recorded
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
    # filled by the listing only (the account cards) - as the invoice will charge, total VAT included
    line_count: int = 0
    subtotal: float = 0
    vat_total: float = 0
    total: float = 0

    class Config:
        from_attributes = True


class OpenAccountLineCreateRequest(BaseModel):
    product_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    sale_unit_id: uuid.UUID | None = None  # None: the product's base unit
    quantity: float = Field(default=1, gt=0)


class OpenAccountLineUpdateRequest(BaseModel):
    quantity: float


class OpenAccountLineUnitRequest(BaseModel):
    sale_unit_id: uuid.UUID | None = None  # None: back to the product's base unit


class OpenAccountLineResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    product_id: uuid.UUID | None
    service_id: uuid.UUID | None
    name_snapshot: str
    quantity: float
    unit_price: float
    sale_unit_id: uuid.UUID | None = None
    unit_factor: float = 1
    unit_code_snapshot: str | None = None
    # filled when the lines are listed - as the invoice will compute them
    vat_rate: float = 0
    line_subtotal: float = 0
    line_vat: float = 0
    line_total: float = 0
    # kitchen (point 34b): status, and who sent the dish, when, in which order of the day
    kitchen_status: str | None = None
    kitchen_modified: bool = False
    cancel_reason: str | None = None
    kitchen_order_number: int | None = None
    sent_at: datetime | None = None
    sent_by_name: str | None = None
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
    pos_id: uuid.UUID | None = None  # the till that cashes the account (any till of its activity)


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


class KitchenOrderResponse(BaseModel):
    id: uuid.UUID
    account_id: uuid.UUID
    number: int
    sent_by_user_id: uuid.UUID
    sent_at: datetime

    class Config:
        from_attributes = True
