"""Pydantic schemas for Service (Video 3)."""
import uuid
from datetime import datetime, time
from pydantic import BaseModel, Field, field_validator


def _validate_code(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Código do serviço não pode estar vazio")
    return cleaned


def _validate_name(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Nome do serviço não pode estar vazio")
    return cleaned


class ServiceCreateRequest(BaseModel):
    code: str
    name: str
    vat_id: uuid.UUID
    service_type_id: uuid.UUID | None = None
    resource_type_id: uuid.UUID | None = None
    description: str | None = None
    unit_of_measure_id: uuid.UUID | None = None
    price: float | None = None
    duration_minutes: int | None = Field(default=None, ge=5, le=1440)
    stay_start_time: time | None = None  # a rate's own hours (Pernoite 22:00 -> 07:30) - both or none
    stay_end_time: time | None = None
    brand: str | None = None
    withholding_tax_id: uuid.UUID | None = None
    not_available_pos: bool = False
    activity_ids: list[uuid.UUID] = []  # the activities whose tills offer it - empty: every activity
    status: str = "ACTIVO"
    exemption_reason_id: uuid.UUID | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        return _validate_code(v)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("price")
    @classmethod
    def validate_price(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Preço não pode ser negativo")
        return v


class ServiceUpdateRequest(ServiceCreateRequest):
    pass


class ServiceResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    vat_id: uuid.UUID
    service_type_id: uuid.UUID | None
    resource_type_id: uuid.UUID | None
    description: str | None
    unit_of_measure_id: uuid.UUID | None
    unit_of_measure_code: str | None = None  # attached by the list: the unit's code (UN, CX...)
    price: float | None
    duration_minutes: int | None = None
    stay_start_time: time | None = None
    stay_end_time: time | None = None
    is_stay_rate: bool = False  # attached by the list: a room rate, sold with its room only (never in the cart)
    brand: str | None
    withholding_tax_id: uuid.UUID | None
    not_available_pos: bool
    activity_ids: list[uuid.UUID] = []
    status: str
    exemption_reason_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    @field_validator("activity_ids", mode="before")
    @classmethod
    def no_activity_means_all(cls, v):
        return v or []

    class Config:
        from_attributes = True
