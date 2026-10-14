"""Faturas de compra - requests (the responses are the service's dicts)."""
import uuid
from datetime import date

from pydantic import BaseModel


class PurchaseInvoiceLineInput(BaseModel):
    product_id: uuid.UUID | None = None
    service_id: uuid.UUID | None = None
    sale_unit_id: uuid.UUID | None = None  # a product line: one of its units (None: its base unit)
    description: str | None = None
    quantity: float
    unit_price: float  # without VAT
    legal_vat_rate_id: uuid.UUID
    exemption_id: uuid.UUID | None = None  # required on an exempt line
    deductible_tax_type: str | None = None  # MFI, INV, OBC, SERV, IMPT, SCE - by default from the line


class PurchaseInvoiceCreateRequest(BaseModel):
    supplier_id: uuid.UUID
    supplier_document: str
    document_date: date
    due_date: date | None = None
    fiscal_period_id: uuid.UUID | None = None
    description: str | None = None
    stock_entry: bool = False  # its products enter warehouse_id (the system's automatic entry)
    warehouse_id: uuid.UUID | None = None
    purchase_type: str = "FT"  # FT, FR, TV, NC
    supplier_hash: str | None = None  # the 4 characters printed on the supplier document
    reference_invoice_id: uuid.UUID | None = None  # a credit note: the invoice it corrects
    lines: list[PurchaseInvoiceLineInput]


class PurchaseInvoiceCancelRequest(BaseModel):
    reason: str
