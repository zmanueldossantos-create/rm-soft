"""
CompanyPermissionSeed - marks that a Permission's default role grants were
already distributed to a company. Without it, re-running the seed (every
app boot) could not tell "never granted yet" from "a GESTOR removed it in
the admin matrix", and would silently give the permission back.
A row means: defaults for (company, permission) were applied once, never again.
"""
from datetime import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CompanyPermissionSeed(Base):
    __tablename__ = "company_permission_seeds"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    permission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("permissions.id"), primary_key=True)
    seeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CompanyPermissionSeed {self.company_id} / {self.permission_id}>"