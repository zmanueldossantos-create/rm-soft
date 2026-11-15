"""Encomendas - requests (the responses are the service's dicts)."""
import uuid
from datetime import datetime

from pydantic import BaseModel


class CustomerOrderLineInput(BaseModel):
    product_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    quantity: float
    unit_price: float | None = None  # without VAT - the article's price when not given
    production_note: str | None = None


class CustomerOrderRequest(BaseModel):
    customer_id: uuid.UUID
    activity_id: uuid.UUID | None = None  # the only activity with Encomendas when not given
    delivery_at: datetime
    delivery_mode: str = "LOJA"  # LOJA | ENTREGA
    delivery_address: str | None = None
    contact_name: str | None = None
    contact_phone: str | None = None
    notes: str | None = None
    lines: list[CustomerOrderLineInput]


class CustomerOrderStatusRequest(BaseModel):
    status: str  # ENCOMENDADA | EM_PRODUCAO | PRONTA


class CustomerOrderCancelRequest(BaseModel):
    reason: str
