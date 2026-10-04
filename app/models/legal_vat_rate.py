"""
LegalVatRate - the legal VAT rate of each SAF-T tax category (ISE 0 %, RED 5 %, NOR 14 %...), platform-wide and
SUPER_ADMIN managed: the rates a company receives for the categories its regime allows, at creation and when its
regime changes. The only place a legal percentage lives - never in the code.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class LegalVatRate(Base):
    __tablename__ = "legal_vat_rates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tax_category: Mapped[str] = mapped_column(String(3), nullable=False, unique=True)  # NOR, RED, INT, ISE, OUT
    name: Mapped[str] = mapped_column(String(50), nullable=False)  # given to the company rate, e.g. "Taxa normal"
    rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
