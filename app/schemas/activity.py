"""
Pydantic schemas for Activity (business line / point of sale within a
Company - e.g. Padaria, Bar, Hotel) - GESTOR configures these, but only
for Modules the company has been granted by SUPER_ADMIN.
"""
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator

SERIES_CODE_PATTERN = re.compile(r"^[A-Z0-9]{1,10}$")


class ActivityCreateRequest(BaseModel):
    module_id: uuid.UUID
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome da atividade nao pode estar vazio")
        return cleaned


class ActivityUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome da atividade nao pode estar vazio")
        return cleaned


class ActivityResponse(BaseModel):
    id: uuid.UUID
    module_id: uuid.UUID
    name: str
    series_code: str
    number_digits: int
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
