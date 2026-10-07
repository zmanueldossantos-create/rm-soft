import uuid
from datetime import datetime

from pydantic import BaseModel


class SupplierCreateRequest(BaseModel):
    name: str
    nif: str | None = None
    phone_number: str | None = None
    email: str | None = None
    address: str | None = None
    payment_terms: str | None = None
    notes: str | None = None


class SupplierUpdateRequest(SupplierCreateRequest):
    pass


class SupplierResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    nif: str | None
    phone_number: str | None
    email: str | None
    address: str | None
    payment_terms: str | None
    notes: str | None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True
