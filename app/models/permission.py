"""
Permission catalog - platform-wide (not per-company), listing every
fine-grained action the app can gate (e.g. "internal_consumption:create",
"suppliers:manage"). Paired with RolePermission (per-company grants) to
replace hardcoded require_role(...) checks with a dynamic, admin-configurable
system - see the "menu dinamico / direitos configuraveis" road-map item.

code follows a "module:action" convention, kept stable once shipped (used as
a lookup key in route dependencies - see require_permission in api/deps.py).
category groups related permissions for the admin screen's display only.

Rollout is deliberately incremental: this catalog and RolePermission exist
alongside the old hardcoded require_role(...) checks used everywhere else;
only a pilot module (Consumo Interno) is wired to check permissions
dynamically at first, to validate the approach before migrating the rest.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, DateTime, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Permission(Base):
    __tablename__ = "permissions"
    __table_args__ = (
        UniqueConstraint("code", name="uq_permission_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Permission {self.code}>"
