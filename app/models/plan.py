"""
Planos and contracts. A Plan (Essencial, Profissional...) is edited by the SUPER_ADMIN: its prices, its limits (see
app.core.plan_features.LIMITS - a missing or null limit means unlimited) and its options. A company's CompanyContract
says which plan it has, how it pays (monthly... lifetime), from when to when, and its add-ons (extra users, shops...).

The contracts are kept: a new contract (a renewal, a change of plan) ends the current one, which stays as history -
exactly one current contract per company (partial unique index).
"""
import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Plan(Base):
    __tablename__ = "plans"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    # prices in Kz; null: not sold that way ("sob cotação" when all are null)
    price_monthly: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_quarterly: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_semiannual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_annual: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    price_lifetime: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # local, paid once
    maintenance_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)  # of the lifetime price, a year
    limits: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"max_users": 3, ...}; null = unlimited
    options: Mapped[list[str]] = mapped_column(ARRAY(String(40)), nullable=False, default=list)
    is_popular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class CompanyContract(Base):
    __tablename__ = "company_contracts"
    __table_args__ = (
        Index("uq_company_contract_current", "company_id", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plans.id"), nullable=False)
    deployment_mode: Mapped[str] = mapped_column(String(10), nullable=False)  # SAAS | LOCAL
    billing: Mapped[str] = mapped_column(String(12), nullable=False)  # plan_features.BILLING_TYPES
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # null: no end (lifetime, or sem data de fim)
    maintenance_until: Mapped[date | None] = mapped_column(Date, nullable=True)  # lifetime: updates and support until
    addons: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)  # {"max_users": 5}: added to the plan's
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)  # the amount agreed for this period
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    plan: Mapped[Plan] = relationship(lazy="selectin")


class CompanyLicense(Base):
    """A licence file imported on a client's server (app/core/license.py): kept as it came - checked again each time it
    is read, so a changed row is worth nothing. The previous ones stay as history."""
    __tablename__ = "company_licenses"
    __table_args__ = (
        Index("uq_company_license_current", "company_id", unique=True, postgresql_where=text("is_current")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    is_current: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    imported_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    imported_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
