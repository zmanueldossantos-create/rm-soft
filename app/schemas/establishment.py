"""Pydantic schemas for Establishment (Video 8, company-scoped)."""
import uuid
from datetime import datetime
from pydantic import BaseModel, field_validator


class EstablishmentRequest(BaseModel):
    code: str
    name: str
    description: str | None = None

    @field_validator("code")
    @classmethod
    def validate_code(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Codigo do estabelecimento nao pode estar vazio")
        return cleaned

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do estabelecimento nao pode estar vazio")
        return cleaned


class EstablishmentResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
