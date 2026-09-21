"""
Pydantic schemas for PointOfSale (POS) CRUD - nested under an Activity.
"""
import uuid

from pydantic import BaseModel


class PosCreateRequest(BaseModel):
    activity_id: uuid.UUID
    name: str
    billetage_enabled: bool = False


class PosUpdateRequest(BaseModel):
    name: str
    billetage_enabled: bool = False


class PointOfSaleResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    activity_id: uuid.UUID
    name: str
    is_active: bool
    billetage_enabled: bool
    is_default: bool = False

    class Config:
        from_attributes = True
