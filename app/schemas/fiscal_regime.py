"""
Pydantic schemas for fiscal regimes (SUPER_ADMIN only) - see FiscalRegime model.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class FiscalRegimeCreateRequest(BaseModel):
    name: str
    description: str | None = None
    allows_nor: bool = True
    allows_red: bool = True
    allows_ise: bool = True
    allows_int: bool = False
    allows_out: bool = False
    required_exemption_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do regime nao pode estar vazio")
        return cleaned


class FiscalRegimeUpdateRequest(BaseModel):
    name: str
    description: str | None = None
    allows_nor: bool
    allows_red: bool
    allows_ise: bool
    allows_int: bool
    allows_out: bool
    required_exemption_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do regime nao pode estar vazio")
        return cleaned


class FiscalRegimeResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    allows_nor: bool
    allows_red: bool
    allows_ise: bool
    allows_int: bool
    allows_out: bool
    required_exemption_id: uuid.UUID | None = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
