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


class CustomerOrderRefund(BaseModel):
    payment_method_id: uuid.UUID
    pos_id: uuid.UUID | None = None  # cash: the till it leaves
    bank_account_id: uuid.UUID | None = None  # a transfer: the account it leaves


class CustomerOrderCancelRequest(BaseModel):
    reason: str
    deposit: str | None = None  # an invoiced order already paid: DEVOLVER | RETER
    refund: CustomerOrderRefund | None = None


class CustomerOrderPayRequest(BaseModel):
    pos_id: uuid.UUID
    amount: float
    payment_method_id: uuid.UUID
    terminal_id: uuid.UUID | None = None


class CustomerOrderDeliverRequest(BaseModel):
    pos_id: uuid.UUID
    payment_method_id: uuid.UUID | None = None
    amount: float | None = None  # an order never invoiced: what its Fatura/Recibo is paid with
    terminal_id: uuid.UUID | None = None
    on_credit: bool = False  # «fica a dever»: nothing received, the Fatura stays to be received
