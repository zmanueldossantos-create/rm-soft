"""
Invoice model.
See specification v6/v7, section 4: Factura, Factura-Recibo, Nota de Credito,
Nota de Debito. ATCUD, hash and QR code are simulated (correct format, not
homologated) until the real AGT signature key is available - see Decision 2,
section 4.4. Status values PENDENTE/POR_ENVIAR/ENVIADA/ERRO per section 4.2.

activity_id ties the invoice to one of the company's Activities (e.g.
Padaria, Bar, Hotel) - see discussion on multi-activity companies. series
is derived from the Activity's series_code at creation time.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Integer, Date, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class InvoiceType(str, enum.Enum):
    FACTURA = "FACTURA"
    FACTURA_RECIBO = "FACTURA_RECIBO"
    NOTA_CREDITO = "NOTA_CREDITO"
    NOTA_DEBITO = "NOTA_DEBITO"
    RECIBO = "RECIBO"
    PRO_FORMA = "PRO_FORMA"


class InvoiceStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    POR_ENVIAR = "POR_ENVIAR"
    ENVIADA = "ENVIADA"
    ERRO = "ERRO"


class DocumentLifecycleStatus(str, enum.Enum):
    """Distinct from InvoiceStatus (AGT submission state) - this tracks the
    document's own fiscal lifecycle (see Video 5: emitting a Nota de Credito
    against a Factura moves the ORIGINAL invoice through these states)."""
    EMITIDO = "EMITIDO"
    RECTIFICADO = "RECTIFICADO"
    RECTIFICADO_PARCIAL = "RECTIFICADO_PARCIAL"
    ANULADO = "ANULADO"


class CreditNoteReason(str, enum.Enum):
    """ANL (anulacao/cancellation) or RTF (rectificacao/correction) - required on every Nota de Credito."""
    ANL = "ANL"
    RTF = "RTF"


class Invoice(Base):
    """
    An invoice, scoped to a Company (tenant). customer_id is nullable -
    a counter sale does not always have a billing customer attached.
    business_date is currently the real calendar date at creation time -
    TEMPORARY, to be replaced once the cash register session (POS module)
    is built, per the interim decision on section 3.1.
    """
    __tablename__ = "invoices"
    __table_args__ = (
        # Series can be shared across document types (e.g. manual mode's
        # year-based code) - each document type keeps its own independent
        # counter, so uniqueness must include document_type_id.
        UniqueConstraint("company_id", "document_type_id", "series", "number", name="uq_invoice_company_doctype_series_number"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    # Optional - only set when the invoice was created through the POS
    # (Caixa) flow. A GESTOR creating an invoice directly (outside a cash
    # session) leaves this null - business_date then falls back to today.
    cash_session_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_sessions.id"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    invoice_type: Mapped[InvoiceType] = mapped_column(Enum(InvoiceType), nullable=False, default=InvoiceType.FACTURA)
    # Links to the platform DocumentType catalog (Configuracoes) and to the DocumentSeries that issued this invoice.
    document_type_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("document_types.id"), nullable=True)
    series: Mapped[str] = mapped_column(String(30), nullable=False)
    number: Mapped[int] = mapped_column(nullable=False)
    # Snapshotted from Activity.number_digits at creation time - see Activity model docstring.
    number_digits: Mapped[int] = mapped_column(nullable=False, default=3)
    business_date: Mapped[date] = mapped_column(Date, nullable=False)  # TEMPORARY: today's date until POS session exists
    subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    vat_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    status: Mapped[InvoiceStatus] = mapped_column(Enum(InvoiceStatus), nullable=False, default=InvoiceStatus.PENDENTE)
    # Fiscal lifecycle - separate from the AGT submission `status` above. See Video 5:
    # a Nota de Credito referencing this invoice moves it to RECTIFICADO/RECTIFICADO_PARCIAL/ANULADO.
    document_status: Mapped[DocumentLifecycleStatus] = mapped_column(Enum(DocumentLifecycleStatus), nullable=False, default=DocumentLifecycleStatus.EMITIDO)

    # Only set on Nota de Credito / Nota de Debito - the invoice being rectified/cancelled.
    reference_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    # Set on a Pro-forma (FP) once it has been converted into a real FT/FR - see
    # convert_pro_forma_to_invoice. A converted FP should no longer be convertible again.
    converted_to_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    credit_note_reason: Mapped[CreditNoteReason | None] = mapped_column(Enum(CreditNoteReason), nullable=True)
    credit_note_cause: Mapped[str | None] = mapped_column(String(60), nullable=True)

    # Payment/commercial terms - see Video 4's full Faturas form.
    payment_term_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_terms.id"), nullable=True)
    payment_method_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_method_catalog.id"), nullable=True)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount_received: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    observations: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Free-text reference to another document (e.g. a customer PO number) - distinct
    # from reference_invoice_id, which is specifically the NC/ND's rectified invoice.
    document_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    discount_global_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    # AGT rule (Ulemo 8.8): withholding applies only to Service lines whose article carries
    # a withholding_tax_id marked "Sujeito", and only when the customer is pessoa coletiva
    # (LegalPersonType.JURIDICA). Reduces the amount actually collected (Valor a Pagar).
    retention_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0)
    # Snapshotted from Company.issuance_mode at creation time - the same pattern as
    # DocumentSeries.issuance_mode, so a document keeps its correct emission mode even if
    # the company later switches modes (see get_or_create_current_series mode-matching fix).
    issuance_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="MANUAL")
    # Incremented each time a PDF is generated for this document - drives the "Original" /
    # "2a via" / "Duplicado" / "Triplicado" mention printed on the PDF (legal requirement:
    # the first printout is the Original, every reprint after that must say so clearly).
    print_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    atcud: Mapped[str] = mapped_column(String(50), nullable=False)  # simulated - section 4.4 Decision 2
    invoice_hash: Mapped[str] = mapped_column(String(255), nullable=False)  # simulated
    qr_code_data: Mapped[str] = mapped_column(String(500), nullable=False)  # simulated payload

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Invoice {self.series}/{self.number} ({self.status})>"
