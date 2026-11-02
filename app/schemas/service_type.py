"""Pydantic schemas for ServiceType (Video 3, company-scoped)."""
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class ServiceTypeRequest(BaseModel):
    name: str
    not_available_sales: bool = False  # «Não mostrar no site»: out of the public catalogue (public API)

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do tipo de serviço não pode estar vazio")
        return cleaned


class ServiceTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    not_available_sales: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
