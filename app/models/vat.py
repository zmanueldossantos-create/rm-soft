"""
VAT model - Angolan legal tax rates (0%, 5%, 14%).
Centralized fiscal module shared across all business sectors -
see specification v6/v7, section 4.5.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class VAT(Base):
    """
    VAT rate, scoped to a Company (tenant).
    Rate stored as a percentage (ex. 14.00 for 14%).
    """
    __tablename__ = "vat_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(50), nullable=False)  # ex. "Taxa normal", "Isento"
    rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)  # ex. 14.00
    # SAF-T TaxCode category (NOR/RED/ISE/INT/OUT) - matches FiscalRegime.allows_* so the
    # product/service VAT dropdown can be filtered to only what the company's CURRENT regime
    # permits, without ever touching already-issued invoices or existing product/service
    # assignments (those keep referencing their own vat_id regardless of later regime changes).
    tax_category: Mapped[str] = mapped_column(String(10), nullable=False, default="NOR")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<VAT {self.name} ({self.rate}%)>"
