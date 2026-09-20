"""
InvoiceLine model.
See specification v6/v7, section 4.5: each line applies the product's VAT
rate at the moment of sale (snapshot, not a live reference) - if the VAT
rate changes later, past invoices must keep their original rate for
fiscal accuracy.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class InvoiceLine(Base):
    """A single line item within an Invoice."""
    __tablename__ = "invoice_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    invoice_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=False, index=True)
    # Exactly one of product_id / service_id is set - a line sells either a physical
    # good (Product) or a Service (see Phase C decision to keep them as separate tables).
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)

    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)  # in case product is edited/deactivated later
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    discount_percent: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    vat_rate_snapshot: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # % at time of sale

    line_subtotal: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_vat: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    line_total: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)

    # Withholding applied on this line, copied when the invoice is issued (like vat_rate_snapshot): later
    # changes of the withholding catalog must not alter an issued document. Empty when nothing was withheld.
    retention_name_snapshot: Mapped[str | None] = mapped_column(String(150), nullable=True)
    retention_rate: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    retention_amount: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<InvoiceLine {self.product_name_snapshot} x{self.quantity}>"
