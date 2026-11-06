"""
Contabilidade - the journals (diários) and their entries (lançamentos).

Journal: VND Vendas, CMP Compras, CX Caixa, BCO Bancos, OD Operações diversas, ABE Abertura by default (made when the
chart of accounts is started) - the company adds, renames or deactivates them; one with entries is never deleted.

JournalEntry: a lançamento of a journal. RASCUNHO (draft: changed freely, no number, counts nowhere) or LANCADO
(posted: debit = credit, numbered per journal and year without gaps - «OD 2026/0001» - and never changed again).
A posted entry is corrected by its estorno: a new posted entry with the same lines reversed, pointing at it
(reversal_of_id). See app.services.journal_service.

JournalEntryLine: one line - an account of the chart (a last-level, active one), a debit or a credit.

An entry made by the system from a document (source_kind / source_id: INVOICE and the invoice) is posted at once and
never changed by hand - see app.services.accounting_integration_service. PendingIntegration: a document the system
could not post yet (an account missing in «Contas por operação», a closed period...), with the reason.
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint, func,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

ENTRY_STATUSES = ("RASCUNHO", "LANCADO")

# the journals every company starts with: code, name
DEFAULT_JOURNALS = (
    ("VND", "Vendas"),
    ("CMP", "Compras"),
    ("CX", "Caixa"),
    ("BCO", "Bancos"),
    ("OD", "Operações diversas"),
    ("ABE", "Abertura"),
)


class Journal(Base):
    __tablename__ = "journals"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_journal_company_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(10), nullable=False)  # never changes once created (the numbers carry it)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    __table_args__ = (
        UniqueConstraint("journal_id", "year", "number", name="uq_journal_entry_number"),
        UniqueConstraint("company_id", "source_kind", "source_id", name="uq_journal_entry_source"),  # once per document
        CheckConstraint("status IN ('RASCUNHO', 'LANCADO')", name="ck_journal_entry_status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    journal_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("journals.id"), nullable=False, index=True)
    entry_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    document_ref: Mapped[str | None] = mapped_column(String(60), nullable=True)  # the supporting document, as typed
    status: Mapped[str] = mapped_column(String(10), default="RASCUNHO", nullable=False)
    # the numbering of the journal for the year of entry_date: set when posted, never before
    year: Mapped[int | None] = mapped_column(Integer, nullable=True)
    number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # the document this entry was made from by the system (None: typed by hand)
    source_kind: Mapped[str | None] = mapped_column(String(20), nullable=True)
    source_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    reversal_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id"), nullable=True, unique=True)  # an entry has one estorno at most
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    posted_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class JournalEntryLine(Base):
    __tablename__ = "journal_entry_lines"
    __table_args__ = (
        CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="ck_journal_line_one_side"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    entry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False, index=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)
    credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0, nullable=False)


class PendingIntegration(Base):
    """A document waiting for its entry: why it could not be posted the last time it was tried."""
    __tablename__ = "pending_integrations"
    __table_args__ = (UniqueConstraint("company_id", "source_kind", "source_id", name="uq_pending_integration_source"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    document: Mapped[str] = mapped_column(String(60), nullable=False)  # «FT A2026/12»
    document_date: Mapped[date] = mapped_column(Date, nullable=False)
    reason: Mapped[str] = mapped_column(String(300), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
