"""
Warehouse model (Armazem / point de stockage).
See specification v6/v7, section 2.8: entity hierarchy includes one or more
warehouses per company. A default warehouse is auto-created for every new
company (see company_service.create_company), mirroring the VAT seeding
pattern - Phase 1 keeps a single default warehouse per company for
simplicity; multi-warehouse selection UI can be added later without
changing this model.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Warehouse(Base):
    __tablename__ = "warehouses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    province_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("provinces.id"), nullable=True)
    municipality_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("municipalities.id"), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    allow_negative_stock: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    entradas_bloqueadas: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    saidas_bloqueadas: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    gerido_por_familia_tipo: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Warehouse {self.name}>"
