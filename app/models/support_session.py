"""
Accesso de suporte (SUPER_ADMIN): the platform enters a client company with the gestor's screens, for a reason, for an
hour at most - never with a company account nor a shared password. Every entry is kept (who, when, why, until when)
and the company's gestor sees them. What is done meanwhile is recorded in the platform user's name.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SupportSession(Base):
    __tablename__ = "support_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    admin_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    reason: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # the one-time code that opens the company's address (another browser tab, in SaaS another domain): hashed, 2 min
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)
    code_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    code_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
