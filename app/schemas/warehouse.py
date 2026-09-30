"""
Pydantic schemas for the company's warehouse.
Phase 1 keeps a single warehouse per company (section 5.2/2.8) - this
schema supports viewing and renaming it, not full multi-warehouse CRUD.
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, field_validator


class WarehouseResponse(BaseModel):
    id: uuid.UUID
    name: str
    code: str | None = None
    province_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    address: str | None = None
    allow_negative_stock: bool = False
    entradas_bloqueadas: bool = False
    saidas_bloqueadas: bool = False
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class WarehouseUpdateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do armazem nao pode estar vazio")
        return cleaned


class WarehouseCreateRequest(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do armazem nao pode estar vazio")
        return cleaned


class WarehouseCreateFullRequest(BaseModel):
    name: str
    code: str | None = None
    province_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    address: str | None = None
    allow_negative_stock: bool = False
    entradas_bloqueadas: bool = False
    saidas_bloqueadas: bool = False

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do armazem nao pode estar vazio")
        return cleaned
