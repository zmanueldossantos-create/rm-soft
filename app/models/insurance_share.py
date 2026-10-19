"""
InsuranceShare (comparticipação) - a pharmacy sale shared with an insurer or an agreement: the patient pays his part
on his own document (a Fatura-Recibo, which hands the goods over), the insurer receives a Fatura for the rest, paid
later by a receipt. One row per shared sale; it links the two documents and keeps the beneficiary's card - the
monthly statement sent to each insurer is built from it (insurance_service).
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InsuranceShare(Base):
    __tablename__ = "insurance_shares"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    insurer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    # None when the insurer pays everything: its Fatura is then the only document of the sale
    patient_invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True, unique=True)
    insurer_invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, unique=True)
    coverage_pct: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    card_number: Mapped[str] = mapped_column(String(60), nullable=False)  # n.º do cartão do beneficiário
    beneficiary_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
