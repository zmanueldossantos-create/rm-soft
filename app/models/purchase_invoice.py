"""
PurchaseInvoice / PurchaseInvoiceLine - a supplier's invoice, registered by the company (Fatura de compra, point 12).

The document is the supplier's: its number (supplier_document, as printed) is kept as given; the company numbers its
own registrations (COMP<year>/<n>) to find them again. Each line has the VAT the supplier charged - a LEGAL rate
(LegalVatRate: NOR 14 %, RED 5 %, ISE 0 %... whatever the company's own regime allows on its sales) with its exemption
motive when exempt. The VAT the company may deduct follows ITS regime (FiscalRegime.input_vat_deductible_pct, kept on
the invoice as it was): the rest of the VAT is a cost, added to the line's cost (HT + non-deductible VAT).

Booked in a period like every internal entry (the active one, or the soft-closed one for a late invoice). Never
deleted: a mistaken registration is cancelled (ANULADA) with its reason - see purchase_invoice_service.

SAF-T (PurchaseInvoices): the supplier document's type (purchase_type: FT, FR, TV or NC - a supplier's credit note,
which refers to the invoice it corrects and counts against the deductible VAT), the 4 characters of its printed hash
(supplier_hash, "0" in the file when empty) and, per line, what the deductible VAT is for (deductible_tax_type: MFI
fixed assets, INV inventory, OBC other consumables, SERV services, IMPT imports, SCE services contracted abroad).

Stock: an invoice may bring its products into a warehouse (warehouse_id) - the system's automatic entry document
(stock_entry_document_id, an EA), each product at its line's cost; its cancellation takes them out again (an SA,
stock_exit_document_id). A product line keeps the unit it was bought in (a sack of 20 kg: unit_factor 20).
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PurchaseInvoiceStatus(str, enum.Enum):
    REGISTADA = "REGISTADA"
    ANULADA = "ANULADA"


class PurchaseInvoice(Base):
    __tablename__ = "purchase_invoices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(20), nullable=False)  # COMP2026 - the company's own registration
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    supplier_document: Mapped[str] = mapped_column(String(60), nullable=False)  # "FT A/123", as printed by the supplier
    purchase_type: Mapped[str] = mapped_column(String(2), nullable=False, default="FT", server_default="FT")
    supplier_hash: Mapped[str | None] = mapped_column(String(4), nullable=True)
    # a credit note (NC): the supplier invoice it corrects
    reference_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_invoices.id"), nullable=True)
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)

    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    deductible_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # the company's regime at registration
    vat_deductible: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_non_deductible: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    # the automatic stock entry of its products (None: the invoice did not touch the stock) and its reversal
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True)
    stock_entry_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movement_documents.id"), nullable=True)
    stock_exit_document_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movement_documents.id"), nullable=True)

    status: Mapped[PurchaseInvoiceStatus] = mapped_column(Enum(PurchaseInvoiceStatus), nullable=False, default=PurchaseInvoiceStatus.REGISTADA)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseInvoiceLine(Base):
    __tablename__ = "purchase_invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    purchase_invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)
    description: Mapped[str] = mapped_column(String(255), nullable=False)
    # a product line: the unit it was bought in (None = the product's base unit), its code and base units per unit
    sale_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_sale_units.id"), nullable=True)
    unit_snapshot: Mapped[str | None] = mapped_column(String(20), nullable=True)
    unit_factor: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False, default=1, server_default="1")
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)  # without VAT
    # the VAT the supplier charged - a legal rate, kept as it was
    legal_vat_rate_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("legal_vat_rates.id"), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(3), nullable=False)
    vat_rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    exemption_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_codes.id"), nullable=True)

    line_subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_vat: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_deductible: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_non_deductible: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    cost: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # HT + non-deductible VAT
    deductible_tax_type: Mapped[str] = mapped_column(String(4), nullable=False, default="OBC", server_default="OBC")
    # the lot received (a product followed by lot / expiry, entering the stock)
    lot_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
