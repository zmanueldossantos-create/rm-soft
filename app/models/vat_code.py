"""
VatCode - the official AGT VAT code catalog (Codigo IVA), platform-wide,
SUPER_ADMIN managed (see reference list: M22/Isento artigo 12 m do CIVA,
M23, M24...) with the exact legal article text and a validity window.

Distinct from the existing company-scoped VAT model (app/models/vat.py)
used today by Products/Invoices for the operational tax rate - reconciling
the two is a separate future step, not part of this base-data setup.
"""
import uuid
from datetime import date, datetime
from sqlalchemy import String, Boolean, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class VatCode(Base):
    __tablename__ = "vat_codes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(10), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    country_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("countries.id"), nullable=False, index=True)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    observations: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<VatCode {self.code} - {self.rate}%>"
