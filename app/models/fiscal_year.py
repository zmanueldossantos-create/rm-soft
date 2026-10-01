"""
Fiscal Year model (Ano).
See specification v6/v7, section 3.4: strict hierarchy - a Period (month) can
only open if its parent Year is open; a Year can only close once its current
Period is closed. Journée commerciale (business_date) is NOT locked here -
it follows its own rule (section 3.1/3.3), tied to cash register sessions
(POS module, not yet built - see interim decision in invoice model).
"""
import uuid
from datetime import datetime

from sqlalchemy import Integer, String, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class FiscalYear(Base):
    """
    A fiscal year, scoped to a Company (tenant).
    is_open: OUVERTA (True) or FECHADA (False) - section 3.4 v6/v7.
    """
    __tablename__ = "fiscal_years"
    __table_args__ = (
        UniqueConstraint("company_id", "year", name="uq_fiscal_year_company_year"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)

    year: Mapped[int] = mapped_column(Integer, nullable=False)  # ex. 2026
    # ABERTO (active), FECHO_PARCIAL (soft-closed: internal late entries only) or FECHADO - see fiscal_period_service.
    status: Mapped[str] = mapped_column(String(15), default="ABERTO", server_default="ABERTO", nullable=False)

    @property
    def is_open(self) -> bool:
        """Open to every operation, automatic ones included: ABERTO only."""
        return self.status == "ABERTO"

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<FiscalYear {self.year} ({'OUVERTA' if self.is_open else 'FECHADA'})>"
