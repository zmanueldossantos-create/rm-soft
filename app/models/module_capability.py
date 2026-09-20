"""
ModuleCapability - which capabilities a Module (sector) gives (see app.core.capabilities).
One row per (module, capability), all of them always present once the module was seeded:
switching a capability off only flips is_enabled, nothing is ever deleted. A module with no
rows was never seeded; a custom module the SUPER_ADMIN created by hand starts with none
(core only) until capabilities are ticked for it.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ModuleCapability(Base):
    __tablename__ = "module_capabilities"

    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("modules.id"), primary_key=True)
    capability: Mapped[str] = mapped_column(String(30), primary_key=True)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<ModuleCapability {self.module_id} {self.capability} {self.is_enabled}>"