"""Pydantic schemas for ServiceType (Video 3, company-scoped)."""
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class ServiceTypeRequest(BaseModel):
    name: str
    not_available_purchases: bool = False
    not_available_pos: bool = False
    not_available_sales: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do tipo de servico nao pode estar vazio")
        return cleaned


class ServiceTypeResponse(BaseModel):
    id: uuid.UUID
    name: str
    not_available_purchases: bool
    not_available_pos: bool
    not_available_sales: bool
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
