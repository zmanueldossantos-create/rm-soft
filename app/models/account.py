"""
Contabilidade - the company's chart of accounts (plano de contas) and the choice it started from.

Account: one account of the chart. Its code says where it sits - «4» (a class), «45» (an account of the class), «45.1»,
«45.1.1» (its sub-accounts): the parent is the code without its last part (45.1.1 -> 45.1 -> 45 -> 4). The code never
changes once created (the entries will point at it); the name may, and an account may be deactivated.

AccountingSettings: how the chart was started - the PGC (Plano Geral de Contabilidade de Angola, loaded from the
system's reference list), the company's own chart (imported from the Excel model), or empty - and when.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base

CHART_SOURCES = ("PGC", "PROPRIO", "VAZIO")


class Account(Base):
    __tablename__ = "accounts"
    __table_args__ = (UniqueConstraint("company_id", "code", name="uq_account_company_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    parent_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("accounts.id"), nullable=True, index=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False)  # 1 a class, 2 an account, 3+ its sub-accounts
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AccountingSettings(Base):
    __tablename__ = "accounting_settings"

    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), primary_key=True)
    chart_source: Mapped[str | None] = mapped_column(String(10), nullable=True)  # PGC, PROPRIO or VAZIO
    chart_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
