"""
User model - phone number authentication (v7).
See specification v7, section 2.4.
A phone number is unique PER company_id, except for SUPER_ADMIN accounts
which are not attached to any company (company_id is NULL).
Role values are in Portuguese (PT-PT) since they are shown directly to end users.
"""
import uuid
from datetime import datetime
import enum

from sqlalchemy import String, Boolean, DateTime, Enum, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class UserRole(str, enum.Enum):
    SUPER_ADMIN = "SUPER_ADMIN"   # Platform-level, no company_id - manages companies/licenses
    GESTOR = "GESTOR"             # was GESTIONNAIRE
    CAIXA = "CAIXA"                # was CAISSIER
    ARMAZENISTA = "ARMAZENISTA"    # was MAGASINIER
    CONTABILISTA = "CONTABILISTA"  # was COMPTABLE
    ATENDENTE = "ATENDENTE"  # contas abertas sans fecho
    COZINHA = "COZINHA"  # the kitchen screen: moves dishes forward, never cashes


class User(Base):
    """
    User attached to a Company (tenant), except SUPER_ADMIN accounts (company_id is NULL).
    Login identifier = phone number (E.164 format), not email.
    """
    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint("company_id", "phone_number", name="uq_user_company_phone"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=True, index=True)

    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    phone_number: Mapped[str] = mapped_column(String(20), nullable=False, index=True)  # E.164 format, ex. +244923456789
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<User {self.phone_number} ({self.role})>"
