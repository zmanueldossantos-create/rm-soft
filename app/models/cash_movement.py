"""
CashMovement model - a treasury movement between cash points (POS), or
between a POS and the "outside world" (bank, cash loss/theft). Distinct
from a POS sale (which goes through Invoice/Payment) - this is pure
cash-position tracking, never touches stock or invoicing.

ARCHITECTURE NOTE: an earlier version of this model supported a separate
CashOffice entity (one company-wide "Caixa Geral") alongside PointOfSale,
with source/destination columns for each. That concept has been retired -
every Activity now gets its own default POS (PointOfSale.is_default=True,
see activity_service.create_activity) which behaves exactly like a regular
POS (sales, transfers, user association) rather than a separate treasury-only
entity. CashMovement now only ever references PointOfSale on both sides.

movement_type meanings:
- TRANSFERENCIA: both source_pos_id and destination_pos_id filled, reason_id
  is NOT required.
- ENTRADA_EXTERNA: only destination_pos_id filled (funds coming from outside
  the system, e.g. owner's cash injection), reason_id IS required.
- SAIDA_EXTERNA: only source_pos_id filled (funds leaving the system, e.g.
  bank deposit, loss/theft), reason_id IS required.

Which side is required, and whether reason_id is mandatory, depends on
movement_type and is validated in cash_movement_service, not here.

status (two-step transfer reception): a TRANSFERENCIA starts as PENDENTE -
the sending POS's cash leaves its drawer immediately (physical reality: the
cashier handed over the cash right away), but the destination POS only
credits it to its own expected balance once someone at that POS confirms
they actually received and counted it (status becomes RECEBIDO). This
mirrors handing cash to a courier vs. the receiving till confirming the
count. ENTRADA_EXTERNA/SAIDA_EXTERNA have no second party to confirm with,
so they are created directly as RECEBIDO. See cash_movement_service for the
reception flow and cash_session_service.close_session for how this status
gates the destination-side credit in the expected balance calculation.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Date, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CashMovementType(str, enum.Enum):
    TRANSFERENCIA = "TRANSFERENCIA"
    ENTRADA_EXTERNA = "ENTRADA_EXTERNA"
    SAIDA_EXTERNA = "SAIDA_EXTERNA"


class CashMovementStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    RECEBIDO = "RECEBIDO"


class CashMovement(Base):
    __tablename__ = "cash_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    movement_type: Mapped[CashMovementType] = mapped_column(Enum(CashMovementType), nullable=False)

    source_pos_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=True, index=True)
    destination_pos_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=True, index=True)

    reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_movement_reasons.id"), nullable=True, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)

    status: Mapped[CashMovementStatus] = mapped_column(Enum(CashMovementStatus), nullable=False, default=CashMovementStatus.RECEBIDO)
    received_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CashMovement {self.movement_type} {self.amount} {self.status}>"
