import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator


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


class ResourceTypeCreateRequest(BaseModel):
    name: str
    requires_service: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = v.strip()
        if not cleaned:
            raise ValueError("O nome e obrigatorio")
        return cleaned


class ResourceTypeUpdateRequest(BaseModel):
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


class BookingStatusUpdateRequest(BaseModel):
    status: str


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

    class Config:
        from_attributes = True


class ResourceStatusResponse(BaseModel):
    resource_id: uuid.UUID
    name: str
    capacity: int | None
    status: str  # LIVRE | OCUPADA | RESERVADA - derived on demand, see resource_status_service
    open_accounts: int
    open_total: float
    opened_at: datetime | None
    booking_id: uuid.UUID | None
    booking_starts_at: datetime | None
    booking_ends_at: datetime | None
    booking_status: str | None
    booking_guest_name: str | None = None
    booking_party_size: int | None = None
