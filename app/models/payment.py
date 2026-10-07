"""
Payment model - one payment line for an Invoice. A sale can be split
across multiple payment methods (e.g. 4000 Kz numerario + 6000 Kz
Multicaixa Express for a 10000 Kz total) - see discussion on split
payments. The sum of an invoice's Payment rows must equal its total.

payment_method_id references PaymentMethodCatalog (the 12 official AGT
PaymentMechanism codes - see that model's docstring). This used to be a
fixed 5-value Python enum on this model; that enum has been retired in
favor of the shared catalog, so a Payment's method is now always one of
the same 12 codes used everywhere else (SAF-T export, NovaFatura's
payment_method_id, the Caixa screen).
"""
import uuid
from datetime import datetime

from sqlalchemy import Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    payment_method_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_method_catalog.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Payment {self.payment_method_id} {self.amount}>"
