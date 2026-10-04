"""
CompanyFiscalRegime - the history of a company's fiscal regimes: each regime with the day it took effect. A row is added
when the company is created with a regime and at every real change (effect at once); the regime of a past period is
read here (company_service.regime_on), never guessed from the current one.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyFiscalRegime(Base):
    __tablename__ = "company_fiscal_regimes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    fiscal_regime_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_regimes.id"), nullable=False)
    valid_from: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
