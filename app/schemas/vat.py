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


