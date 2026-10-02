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

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_consumption_reasons_company_name_ci", ConsumptionReasonCatalog.company_id, _func.lower(ConsumptionReasonCatalog.name), unique=True)
