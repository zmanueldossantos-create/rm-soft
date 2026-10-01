"""
StockMovement - internal audit log of every stock quantity change (reception, transfer,
loss, adjustment, sale deduction, production) - one row per warehouse per change, used to
answer "who moved what, when, and why" (Historico de Stock). This is DISTINCT from the
printable Entrada/Saida DOCUMENT concept (see stock_movement_document.py) - this table is
the low-level ledger; the document is the paper trail a user fills in and prints.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, Boolean, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class MovementType(str, enum.Enum):
    RECEPCAO = "RECEPCAO"
    TRANSFERENCIA = "TRANSFERENCIA"
    PERDA = "PERDA"
    AJUSTE = "AJUSTE"
    SAIDA = "SAIDA"
    PRODUCAO = "PRODUCAO"


class LossCategory(str, enum.Enum):
    EXPIRACAO = "EXPIRACAO"
    QUEBRA = "QUEBRA"
    ROUBO = "ROUBO"
    OUTRO = "OUTRO"


class StockMovement(Base):
    __tablename__ = "stock_movements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # The fiscal period it is booked in (late entries may go to the soft-closed month) - see resolve_posting_period.
    fiscal_period_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=True, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)

    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    reference: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # TRANSFERENCIA only - the other side of the transfer, and whether THIS row is the
    # outgoing (source) or incoming (destination) leg (each transfer writes 2 rows).
    counterpart_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True)
    is_transfer_source: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # PERDA only.
    loss_category: Mapped[LossCategory | None] = mapped_column(Enum(LossCategory), nullable=True)

    # PRODUCAO only - True for the finished-goods row, False for each consumed ingredient row.
    is_production_output: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<StockMovement {self.movement_type} {self.quantity}>"
