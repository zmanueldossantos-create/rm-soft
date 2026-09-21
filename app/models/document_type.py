"""
DocumentType catalog - platform-wide, SUPER_ADMIN managed (see Video 4:
AC-Aviso Cobranca, FT-Fatura, FP-Fatura Pro-forma, FR-Fatura/Recibo,
GR-Guia de Remessa, GT-Guia de Transporte, NC-Nota Credito, ND-Nota
Debito, OR-Orcamento). The "code" here also maps to the SAF-T WorkType
where applicable (see PP = Pro-forma seen in the reference SAF-T export).
"""
import enum
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, Enum, SmallInteger, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class DocumentTypeArea(str, enum.Enum):
    """Which functional area a document type belongs to (see reference series table:
    Facturacao / Tesouraria / Compras columns)."""
    FACTURACAO = "FACTURACAO"
    TESOURARIA = "TESOURARIA"
    COMPRAS = "COMPRAS"


class DocumentType(Base):
    __tablename__ = "document_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(4), nullable=False, unique=True)
    area: Mapped[DocumentTypeArea | None] = mapped_column(Enum(DocumentTypeArea), nullable=True)
    # Only these types are selectable when the company is in ELETRONICA mode - the AGT
    # electronic invoicing subset (AF, FT, FR, NC, ND, RC) is narrower than the full catalog.
    electronic_eligible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # SAF-T distinguishes SalesInvoices (fiscal, ATCUD, submitted to AGT) from
    # WorkingDocuments (non-fiscal: Orcamento, Guias, Pro-forma...) - see the InvoiceType
    # vs WorkType enums in the XSD. Administrable by SUPER_ADMIN.
    is_fiscal: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Behaviour of the document, read by the code instead of comparing document types by name.
    # rules_locked: the fiscal rules of an official type - shown, not editable.
    rules_locked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saft_section: Mapped[str] = mapped_column(String(10), default="NONE", nullable=False)  # INVOICES | PAYMENTS | WORKING | NONE
    revenue_sign: Mapped[int] = mapped_column(SmallInteger, default=0, nullable=False)  # +1 sale, -1 credit note, 0 not counted
    requires_origin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # refers to an origin document
    has_lines: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # article lines (a receipt has none)
    paid_on_issue: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sent_to_agt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    deducts_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepts_credit_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepts_debit_note: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    accepts_receipt: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    convertible: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # can become a FT / FR
    issuable_in_invoices: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Nova Fatura
    issuable_at_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # Caixa
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<DocumentType {self.code}>"
