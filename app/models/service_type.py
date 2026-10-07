"""
ServiceType - company-scoped catalog (Video 3: "Tipo de Servico") -
mirrors ProductCategory but for services (e.g. "Alojamento", "Lavandaria"
for a hotel; company-specific, not platform-managed).
"""
import uuid
from datetime import datetime
from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class ServiceType(Base):
    __tablename__ = "service_types"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    not_available_purchases: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    not_available_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    not_available_sales: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ServiceType {self.name}>"
