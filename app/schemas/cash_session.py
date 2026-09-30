"""
Pydantic schemas for CashSession (Caixa open/close) and the POS checkout
flow (cart + split payments -> Invoice, see pos_service).
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


from app.schemas.invoice import InvoiceLineCreateRequest


class OpenSessionRequest(BaseModel):
    pos_id: uuid.UUID
    # Optional - when omitted, the float carries over from this POS's last closed
    # session (see cash_session_service.open_session docstring). Still accepted
    # explicitly for the rare manual-correction case.
    opening_amount: float | None = None

    @field_validator("opening_amount")
    @classmethod
    def validate_opening_amount(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Fundo de caixa nao pode ser negativo")
        return v


class CloseSessionRequest(BaseModel):
    # Optional: when the POS has billetage_enabled, this is ignored and the
    # amount is instead derived from the latest FECHO denomination count -
    # see cash_session_service.close_session.
    closing_amount_counted: float | None = None
    closing_notes: str | None = None

    @field_validator("closing_amount_counted")
    @classmethod
    def validate_closing_amount(cls, v: float | None) -> float | None:
        if v is not None and v < 0:
            raise ValueError("Valor contado nao pode ser negativo")
        return v


class CashSessionResponse(BaseModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    pos_id: uuid.UUID
    business_date: date
    opened_by_user_id: uuid.UUID
    opened_at: datetime
    opening_amount: float
    closed_by_user_id: uuid.UUID | None
    closed_at: datetime | None
    closing_amount_expected: float | None
    closing_amount_counted: float | None
    closing_difference: float | None
    closing_notes: str | None
    status: str

    class Config:
        from_attributes = True


class CheckoutPaymentInput(BaseModel):
    payment_method_id: uuid.UUID
    amount: float

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Valor do pagamento deve ser maior que zero")
        return v


class CheckoutLineInput(InvoiceLineCreateRequest):
    """A Caixa sale line IS an invoice sale line (same fields, sale unit included) - only its own rule below is added."""

    @field_validator("service_id")
    @classmethod
    def validate_exactly_one_item(cls, v, info):
        product_id = info.data.get("product_id")
        if bool(v) == bool(product_id):
            raise ValueError("Cada linha deve referenciar exatamente um produto OU um servico")
        return v


class CheckoutRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    invoice_type: str = "FACTURA"
    discount_global_percent: float = 0
    payment_term_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    bank_account_id: uuid.UUID | None = None
    due_date: date | None = None
    lines: list[CheckoutLineInput]
    payments: list[CheckoutPaymentInput] = []

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A venda deve ter pelo menos uma linha")
        return v

    # NOTE: payments is intentionally allowed to be empty even for FACTURA_RECIBO/
    # PRO_FORMA - a company may have zero payment methods marked available_at_pos
    # (CompanyPaymentMethodPreference), in which case the Caixa screen lets the sale
    # go through without recording a split payment. invoice_service.create_invoice
    # only enforces the payments-sum-equals-total check when payments is non-empty -
    # see the "if payments:" comment there.


class CreateProFormaRequest(BaseModel):
    customer_id: uuid.UUID | None = None
    discount_global_percent: float = 0
    lines: list[CheckoutLineInput]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A pro-forma deve ter pelo menos uma linha")
        return v


class LiquidatePendingInvoiceRequest(BaseModel):
    pro_forma_id: uuid.UUID
    target_invoice_type: str
    payments: list[CheckoutPaymentInput]
