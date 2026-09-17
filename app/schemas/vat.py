"""
Pydantic schemas for VAT rates.
"""
import uuid

from pydantic import BaseModel


class VatResponse(BaseModel):
    id: uuid.UUID
    name: str
    rate: float
    tax_category: str
    is_active: bool

    class Config:
        from_attributes = True


class VatRateCreateRequest(BaseModel):
    name: str
    rate: float
    tax_category: str


class VatRateUpdateRequest(BaseModel):
    name: str
    rate: float
    tax_category: str
