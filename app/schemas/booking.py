import uuid
from datetime import datetime, time

from pydantic import BaseModel, Field, field_validator, model_validator


class ResourceCreateRequest(BaseModel):
    activity_id: uuid.UUID
    resource_type_id: uuid.UUID
    name: str
    capacity: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome e obrigatorio")
        return cleaned


class _ResourceTypeHours(BaseModel):
    """The usual entry / exit hours of a booking of this type (14:00 -> 12:00 for a room): both or neither."""
    default_start_time: time | None = None
    default_end_time: time | None = None

    @model_validator(mode="after")
    def both_or_neither(self):
        if (self.default_start_time is None) != (self.default_end_time is None):
            raise ValueError("Indique a hora de entrada e a hora de saída, ou nenhuma")
        return self


class ResourceTypeCreateRequest(_ResourceTypeHours):
    name: str
    requires_service: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome e obrigatorio")
        return cleaned


class ResourceTypeUpdateRequest(_ResourceTypeHours):
    name: str
    requires_service: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome e obrigatorio")
        return cleaned


class ResourceTypeResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    requires_service: bool
    default_start_time: time | None = None
    default_end_time: time | None = None
    is_active: bool

    class Config:
        from_attributes = True


class ResourceUpdateRequest(BaseModel):
    name: str
    capacity: int | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome e obrigatorio")
        return cleaned


class ResourceResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    activity_id: uuid.UUID
    resource_type_id: uuid.UUID
    name: str
    capacity: int | None
    is_active: bool

    class Config:
        from_attributes = True


class BookingCreateRequest(BaseModel):
    resource_id: uuid.UUID
    starts_at: datetime
    ends_at: datetime
    customer_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    notes: str | None = None
    guest_name: str | None = Field(default=None, max_length=150)
    party_size: int | None = Field(default=None, ge=1, le=1000)


class BookingRescheduleRequest(BaseModel):
    starts_at: datetime
    ends_at: datetime
    service_id: uuid.UUID | None = None
    notes: str | None = None
    customer_id: uuid.UUID | None = None
    guest_name: str | None = Field(default=None, max_length=150)
    party_size: int | None = Field(default=None, ge=1, le=1000)


class BookingChargePaymentInput(BaseModel):
    payment_method_id: uuid.UUID
    amount: float


class BookingChargeRequest(BaseModel):
    """Cobrar uma marcação: the till that cashes it, the payments and the customer of the invoice (none: Consumidor final)."""
    pos_id: uuid.UUID
    payments: list[BookingChargePaymentInput]
    customer_id: uuid.UUID | None = None


class BookingStatusUpdateRequest(BaseModel):
    status: str


class BookingChargeResponse(BaseModel):
    booking: "BookingResponse"
    invoice_id: uuid.UUID


class BookingResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    resource_id: uuid.UUID
    customer_id: uuid.UUID | None
    service_id: uuid.UUID | None
    starts_at: datetime
    ends_at: datetime
    status: str
    notes: str | None
    guest_name: str | None = None
    party_size: int | None = None
    created_by_user_id: uuid.UUID
    created_at: datetime
    invoice_id: uuid.UUID | None = None  # a prepaid passage, or a marcação charged: its invoice
    checked_out_at: datetime | None = None
    # a stay in progress: its open account and what it will cost (listing only)
    stay_account_id: uuid.UUID | None = None
    stay_account_total: float | None = None

    class Config:
        from_attributes = True


class ResourceStatusResponse(BaseModel):
    resource_id: uuid.UUID
    name: str
    capacity: int | None
    status: str  # LIVRE | OCUPADA | RESERVADA - derived on demand, see resource_status_service
    open_accounts: int
    open_total: float
    ready_dishes: int = 0  # dishes the kitchen has made ready on this table
    opened_at: datetime | None
    booking_id: uuid.UUID | None
    booking_starts_at: datetime | None
    booking_ends_at: datetime | None
    booking_status: str | None
    booking_guest_name: str | None = None
    booking_party_size: int | None = None
    stay_ends_at: datetime | None = None  # a stay in progress: its planned end
    stay_overdue_minutes: int = 0  # ... and how far beyond it


BookingChargeResponse.model_rebuild()
