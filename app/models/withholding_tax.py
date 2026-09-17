"""
WithholdingTax (Retencao) catalog - platform-wide, SUPER_ADMIN managed
(Video 3: Sem Retencoes, Retencao na fonte imposto industrial 6.5%,
Imposto Predial 15%) - only applicable to pessoa coletiva customers/services.
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, Numeric, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class WithholdingTax(Base):
    __tablename__ = "withholding_taxes"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    rate: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<WithholdingTax {self.name} - {self.rate}%>"
