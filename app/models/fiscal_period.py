"""
Fiscal Period model (Período - calendar month).
See specification v6/v7, section 3.4: strict hierarchy enforced at the
service layer (fiscal_period_service.py) - a Period can only open if its
parent Year is open; the Year can only close once its current Period is closed.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class FiscalStatus(str, enum.Enum):
    ABERTO = "ABERTO"                # the active one: every operation
    FECHO_PARCIAL = "FECHO_PARCIAL"  # soft-closed: internal late entries only
    FECHADO = "FECHADO"              # final, never reopened


class FiscalPeriod(Base):
    """
    A calendar month within a FiscalYear.
    is_open: OUVERTO (True) or FECHADO (False) - section 3.4 v6/v7.
    """
    __tablename__ = "fiscal_periods"
    __table_args__ = (
        UniqueConstraint("fiscal_year_id", "month", name="uq_fiscal_period_year_month"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    fiscal_year_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_years.id"), nullable=False, index=True)

    month: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-12
    # ABERTO (active), FECHO_PARCIAL (soft-closed: internal late entries only) or FECHADO - see fiscal_period_service.
    status: Mapped[str] = mapped_column(String(15), default="ABERTO", server_default="ABERTO", nullable=False)

    @property
    def is_open(self) -> bool:
        """Open to every operation, automatic ones included: ABERTO only."""
        return self.status == "ABERTO"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FiscalPeriod {self.month} ({'OUVERTO' if self.is_open else 'FECHADO'})>"
