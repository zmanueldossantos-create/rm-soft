"""
RolePermission - per-company grant of a Permission to a UserRole. Absence of
a row for (company_id, role, permission_id) means "not granted" - the seed
step (see permission_service.seed_default_permissions) inserts one row per
role/permission pair reproducing today's hardcoded require_role(...) checks
exactly, so migrating a route to the dynamic system changes nothing for
existing companies until a GESTOR actually edits the matrix.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models.user import UserRole


class RolePermission(Base):
    __tablename__ = "role_permissions"
    __table_args__ = (
        UniqueConstraint("company_id", "role", "permission_id", name="uq_role_permission_company_role_permission"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    permission_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("permissions.id"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<RolePermission {self.role} -> {self.permission_id}>"
