"""
CashSession model - a cash register open/close cycle for one Activity.
See specification section 3.1/3.3: the "journee commerciale" (business
date) is tied to this session's lifecycle, not to the real calendar date
at each sale - this was the interim decision noted on Invoice.business_date
since the very first version of this project, now finally implemented.

A session is opened by a CAIXA/GESTOR with a starting cash float
(fundo de caixa), and closed with the counted cash - the difference
between expected (opening + cash sales) and counted is recorded, never
silently corrected, so discrepancies are always visible for review.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, Enum, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CashSessionStatus(str, enum.Enum):
    ABERTA = "ABERTA"
    FECHADA = "FECHADA"


class CashSession(Base):
    __tablename__ = "cash_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # Denormalized from pos.activity_id at open_session time - kept so existing
    # per-activity queries/reports (list_sessions filter, etc.) need no join.
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    # The actual point of sale this session belongs to - "one open session at
    # a time" is now enforced per POS, not per Activity, so several POS under
    # the same Activity can each run their own cash register independently.
    pos_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=False, index=True)

    # The commercial date this session covers - every invoice created
    # under this session uses THIS date, not date.today() at sale time,
    # so a session spanning midnight (e.g. a bar open late) stays on the
    # day it was opened.
    business_date: Mapped[date] = mapped_column(Date, nullable=False)

    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    opening_amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # fundo de caixa inicial

    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Expected = opening_amount + sum of NUMERARIO (cash) payments during the session - computed at close time.
    closing_amount_expected: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)
    closing_amount_counted: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # what the cashier physically counted
    closing_difference: Mapped[float | None] = mapped_column(Numeric(14, 2), nullable=True)  # counted - expected, signed
    closing_notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    status: Mapped[CashSessionStatus] = mapped_column(Enum(CashSessionStatus), nullable=False, default=CashSessionStatus.ABERTA)

    def __repr__(self) -> str:
        return f"<CashSession {self.business_date} ({self.status})>"
