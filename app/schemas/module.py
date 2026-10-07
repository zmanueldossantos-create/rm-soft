"""
Pydantic schemas for the Module catalog (SUPER_ADMIN only).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class ModuleCreateRequest(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do modulo nao pode estar vazio")
        return cleaned


class ModuleUpdateRequest(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do modulo nao pode estar vazio")
        return cleaned


class ModuleResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class ModuleCapabilitiesRequest(BaseModel):
    capabilities: list[str]


class ModuleCapabilitiesResponse(BaseModel):
    module_id: uuid.UUID
    capabilities: list[str]


class AdminOverviewResponse(BaseModel):
    enforce_capabilities: bool = False
    core: dict
    capabilities: list[dict]
    modules: list[dict]
    companies: list[dict]
    impact: list[dict]
