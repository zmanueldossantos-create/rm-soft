import uuid
from datetime import datetime

from pydantic import BaseModel


class ConsumptionReasonCreateRequest(BaseModel):
    name: str


class ConsumptionReasonUpdateRequest(BaseModel):
    name: str


class ConsumptionReasonResponse(BaseModel):
    id: uuid.UUID
    company_id: uuid.UUID
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class InternalConsumptionCreateRequest(BaseModel):
    activity_id: uuid.UUID
    product_id: uuid.UUID
    quantity: float
    reason_id: uuid.UUID
    resource_id: uuid.UUID | None = None
    notes: str | None = None


class InternalConsumptionEntry(BaseModel):
    id: uuid.UUID
    product_name: str
    product_code: str
    quantity: float
    resource_name: str | None
    consumed_by_name: str
    notes: str | None
    created_at: datetime
