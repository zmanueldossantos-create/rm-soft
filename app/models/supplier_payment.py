"""
SupplierPayment / SupplierPaymentAllocation - what the company pays its suppliers (point 3): one payment (PAG2026/1) for
one supplier, settling one or several of its invoices (FT), fully or in part - each allocation says how much goes to
which invoice. Not a fiscal document (no AGT, no SAF-T: the SAF-T Payments are the customers' receipts).

The money leaves by a payment method allowed for payments: in cash from a till (an automatic exit of that till, which
lowers what its drawer should hold), by transfer or cheque from one of the company's bank accounts (recorded only).
Never deleted: cancelled with its reason - the invoices are owed again and the cash goes back into the till.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupplierPaymentStatus(str, enum.Enum):
    REGISTADO = "REGISTADO"
    ANULADO = "ANULADO"


class SupplierPayment(Base):
    __tablename__ = "supplier_payments"
    __table_args__ = (UniqueConstraint("company_id", "series", "number", name="uq_supplier_payment_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("suppliers.id"), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(20), nullable=False)  # PAG2026
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    payment_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # the sum of its allocations
    payment_method_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_method_catalog.id"), nullable=False)
    bank_account_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=True)
    pos_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=True)  # cash: the till
    cash_movement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_movements.id"), nullable=True)
    reversal_movement_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_movements.id"), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(60), nullable=True)  # cheque or transfer number
    notes: Mapped[str | None] = mapped_column(String(300), nullable=True)

    status: Mapped[SupplierPaymentStatus] = mapped_column(Enum(SupplierPaymentStatus), nullable=False, default=SupplierPaymentStatus.REGISTADO)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class SupplierPaymentAllocation(Base):
    __tablename__ = "supplier_payment_allocations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    payment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("supplier_payments.id"), nullable=False, index=True)
    purchase_invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("purchase_invoices.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
