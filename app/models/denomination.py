"""
Denomination catalog - platform-wide, SUPER_ADMIN managed (see Bank/Currency
for the same pattern). The physical notes/coins for a given currency (e.g.
Kwanza banknotes: 200, 500, 1000, 2000, 5000, 10000; coins: 1, 5, 10, 20, 50)
- used by the Moedeiro (billetage) feature to count cash by denomination
instead of a single lump sum.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Numeric, Boolean, DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class DenominationType(str, enum.Enum):
    NOTA = "NOTA"
    MOEDA = "MOEDA"


class Denomination(Base):
    __tablename__ = "denominations"
    __table_args__ = (
        UniqueConstraint("currency_id", "value", "denomination_type", name="uq_denomination_currency_value_type"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=False, index=True)
    value: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    denomination_type: Mapped[DenominationType] = mapped_column(Enum(DenominationType), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Denomination {self.value} ({self.denomination_type})>"
