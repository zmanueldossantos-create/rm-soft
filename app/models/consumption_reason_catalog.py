"""
ConsumptionReasonCatalog - managed catalog of reasons for internal stock
consumption (e.g. "Limpeza de quarto", "Reposicao de amenities",
"Quebra/Perda", "Uso administrativo"). Same pattern as
ResourceTypeCatalog/CashMovementReason - see Categorias.jsx's generic
catalog CRUD, which this is managed through (not a standalone screen).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ConsumptionReasonCatalog(Base):
    __tablename__ = "consumption_reason_catalog"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_consumption_reason_company_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ConsumptionReasonCatalog {self.name}>"
