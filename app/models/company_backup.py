"""
Cópias de segurança de uma empresa: its settings (automatic at 1 to 3 hours a day, or manual only) and the copies made
(company_backup_jobs). Each copy is the file «Exportar» makes, kept on the server in BACKUP_DIR/<company id>/ - never
under /uploads, which the web serves: a copy holds the company's clients and password hashes.
"""
import uuid
from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class CompanyBackupSettings(Base):
    __tablename__ = "company_backup_settings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, unique=True, index=True)
    mode: Mapped[str] = mapped_column(String(10), nullable=False, default="MANUAL")  # AUTOMATICA | MANUAL
    times: Mapped[list[str]] = mapped_column(ARRAY(String(5)), nullable=False, default=list)  # "HH:MM", Luanda, 1 to 3
    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CompanyBackup(Base):
    __tablename__ = "company_backups"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)  # AUTOMATICA | MANUAL | PLATAFORMA (the super admin)
    status: Mapped[str] = mapped_column(String(10), nullable=False)  # FEITA | ERRO
    file_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    error: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), index=True)
