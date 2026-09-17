"""
CashDenominationCount / CashDenominationCountLine - a physical cash count by
denomination for a CashSession (Moedeiro / billetage feature). Only used
when the session's POS has billetage_enabled=True.

count_type meanings:
- ABERTURA: counted when opening the session (optional, informational).
- FECHO: counted when closing the session - if present, close_session uses
  the sum of its lines instead of asking for a single manual amount.
- TROCA: a denomination exchange (troco) - recomposing the drawer's physical
  mix without changing the total (e.g. breaking a 5000 note into five 1000
  notes). Net amount is always 0 by construction, tracked via two linked
  counts (out/in) rather than a single one - see cash_denomination_service.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Numeric, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class DenominationCountType(str, enum.Enum):
    ABERTURA = "ABERTURA"
    FECHO = "FECHO"
    TROCA_SAIDA = "TROCA_SAIDA"
    TROCA_ENTRADA = "TROCA_ENTRADA"


class CashDenominationCount(Base):
    __tablename__ = "cash_denomination_counts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    cash_session_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_sessions.id"), nullable=False, index=True)
    count_type: Mapped[DenominationCountType] = mapped_column(Enum(DenominationCountType), nullable=False)
    counted_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    counted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CashDenominationCount {self.count_type}>"


class CashDenominationCountLine(Base):
    __tablename__ = "cash_denomination_count_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    count_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_denomination_counts.id"), nullable=False, index=True)
    denomination_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("denominations.id"), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)

    def __repr__(self) -> str:
        return f"<CashDenominationCountLine x{self.quantity}>"
