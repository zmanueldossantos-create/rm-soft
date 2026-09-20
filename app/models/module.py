"""
Module catalog - platform-wide reference list of business module types
(Hotel, Padaria, Bar, Restaurante - extensible later, e.g. Farmacia).
Managed by SUPER_ADMIN. A company is granted access to specific modules
(see CompanyModule); the GESTOR then configures the concrete Activity
(name, invoice series, number padding) for each module the company has
been granted - see discussion on multi-activity companies.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Module(Base):
    __tablename__ = "modules"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)  # e.g. "Hotel", "Padaria"
    # Stable sector code (app.core.capabilities.SECTORS: HOTEL, BAR...) - null for a module the
    # SUPER_ADMIN created by hand. Names stay free; behaviour comes from ModuleCapability rows.
    code: Mapped[str | None] = mapped_column(String(30), nullable=True, unique=True)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Module {self.name}>"
