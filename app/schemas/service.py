"""Pydantic schemas for Service (Video 3)."""
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


def _validate_code(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Codigo do servico nao pode estar vazio")
    return cleaned


def _validate_name(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Nome do servico nao pode estar vazio")
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
    brand: str | None = None
    withholding_tax_id: uuid.UUID | None = None
    subject_to_return: bool = False
    not_available_pos: bool = False
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
            raise ValueError("Preco nao pode ser negativo")
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
    price: float | None
    brand: str | None
    withholding_tax_id: uuid.UUID | None
    subject_to_return: bool
    not_available_pos: bool
    status: str
    exemption_reason_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
