"""
CashMovementReason catalog - company-scoped, managed by GESTOR (not
SUPER_ADMIN, unlike most other catalogs - these are business-specific:
"Deposito bancario", "Eletricidade", "Perda/Roubo", etc). Required on
every external CashMovement (ENTRADA_EXTERNA / SAIDA_EXTERNA), never on
an internal TRANSFERENCIA between two cash points (see CashMovement).

Reuses MovementDirection (ENTRADA/SAIDA) from movement_type.py rather than
defining a duplicate enum with identical meaning.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models.movement_type import MovementDirection


class CashMovementReason(Base):
    __tablename__ = "cash_movement_reasons"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_cash_movement_reason_company_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Deposito bancario", "Eletricidade"
    direction: Mapped[MovementDirection] = mapped_column(Enum(MovementDirection), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CashMovementReason {self.name} ({self.direction})>"
