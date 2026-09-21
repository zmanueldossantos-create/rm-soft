"""
Pydantic schemas for invoices.
See specification v6/v7, section 4.
"""
import uuid
from datetime import date, datetime

from pydantic import BaseModel, field_validator


class InvoiceLineCreateRequest(BaseModel):
    product_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    quantity: float
    discount_percent: float = 0

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade deve ser maior que zero")
        return v

    @field_validator("service_id")
    @classmethod
    def validate_exactly_one_item(cls, v, info):
        product_id = info.data.get("product_id")
        if bool(v) == bool(product_id):
            raise ValueError("Cada linha deve referenciar exatamente um produto OU um servico")
        return v


class InvoiceCreateRequest(BaseModel):
    activity_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    invoice_type: str = "FACTURA"
    business_date: date | None = None
    payment_term_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    bank_account_id: uuid.UUID | None = None
    due_date: date | None = None
    amount_received: float | None = None
    payment_date: date | None = None
    observations: str | None = None
    document_reference: str | None = None
    discount_global_percent: float = 0
    lines: list[InvoiceLineCreateRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A fatura deve ter pelo menos uma linha")
        return v


class InvoiceLineResponse(BaseModel):
    id: uuid.UUID
    product_id: uuid.UUID | None
    service_id: uuid.UUID | None
    product_name_snapshot: str
    quantity: float
    unit_price: float
    discount_percent: float
    vat_rate_snapshot: float
    line_subtotal: float
    line_vat: float
    line_total: float
    retention_name_snapshot: str | None = None
    retention_rate: float | None = None
    retention_amount: float | None = None
    exemption_code: str | None = None

    class Config:
        from_attributes = True


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    activity_id: uuid.UUID
    customer_id: uuid.UUID | None
    invoice_type: str
    series: str
    number: int
    number_digits: int
    business_date: date
    subtotal: float
    vat_total: float
    total: float
    status: str
    document_status: str
    document_type_id: uuid.UUID | None
    reference_invoice_id: uuid.UUID | None
    credit_note_reason: str | None
    credit_note_cause: str | None
    due_date: date | None
    payment_term_id: uuid.UUID | None
    payment_method_id: uuid.UUID | None
    bank_account_id: uuid.UUID | None
    amount_received: float | None
    payment_date: date | None
    observations: str | None
    discount_global_percent: float
    retention_total: float
    document_reference: str | None
    issuance_mode: str
    item_count: int = 0
    converted_to_invoice_id: uuid.UUID | None = None
    atcud: str
    invoice_hash: str
    qr_code_data: str
    created_at: datetime

    class Config:
        from_attributes = True


class InvoiceDetailResponse(InvoiceResponse):
    lines: list[InvoiceLineResponse]


class CreditNoteLineRequest(BaseModel):
    invoice_line_id: uuid.UUID
    quantity: float

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Quantidade a creditar deve ser maior que zero")
        return v


class CreditNoteCreateRequest(BaseModel):
    activity_id: uuid.UUID
    reference_invoice_id: uuid.UUID
    credit_note_reason: str  # "ANL" ou "RTF"
    credit_note_cause: str
    lines: list[CreditNoteLineRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A nota de credito deve ter pelo menos uma linha")
        return v

    @field_validator("credit_note_cause")
    @classmethod
    def validate_cause(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("A causa da nota de credito e obrigatoria")
        if len(cleaned) > 60:
            raise ValueError("A causa da nota de credito deve ter no maximo 60 caracteres")
        return cleaned


class DebitNoteCreateRequest(BaseModel):
    activity_id: uuid.UUID
    reference_invoice_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    document_reference: str | None = None
    observations: str | None = None
    lines: list[InvoiceLineCreateRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A nota de debito deve ter pelo menos uma linha")
        return v


class ReceiptCreateRequest(BaseModel):
    activity_id: uuid.UUID
    reference_invoice_id: uuid.UUID
    amount: float
    document_reference: str | None = None
    observations: str | None = None

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("O valor do recibo deve ser maior que zero")
        return v


class ProFormaCreateRequest(BaseModel):
    activity_id: uuid.UUID
    customer_id: uuid.UUID | None = None
    document_reference: str | None = None
    observations: str | None = None
    discount_global_percent: float = 0
    lines: list[InvoiceLineCreateRequest]

    @field_validator("lines")
    @classmethod
    def validate_lines(cls, v: list) -> list:
        if not v:
            raise ValueError("A pro-forma deve ter pelo menos uma linha")
        return v


class ConvertProFormaRequest(BaseModel):
    target_invoice_type: str  # "FACTURA" or "FACTURA_RECIBO"
    payment_term_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    bank_account_id: uuid.UUID | None = None
    due_date: date | None = None
