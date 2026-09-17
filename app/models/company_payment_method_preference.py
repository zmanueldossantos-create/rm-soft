"""
CompanyPaymentMethodPreference - per-company choice of which
PaymentMethodCatalog codes (the 12 official AGT ones) appear as selectable
on that company's Caixa screen. Managed by each company's own GESTOR, not
SUPER_ADMIN - see discussion on why available_at_pos could not live
directly on the shared PaymentMethodCatalog table (that table is platform-
wide, one row per code shared by every company; a flag there would affect
all companies at once instead of letting each GESTOR choose independently).

One row per (company_id, payment_method_id) pair - absence of a row means
"not available at POS for this company" (default off, same as the old
available_at_pos default before this split).
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class CompanyPaymentMethodPreference(Base):
    __tablename__ = "company_payment_method_preferences"
    __table_args__ = (
        UniqueConstraint("company_id", "payment_method_id", name="uq_company_payment_method_pref"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    payment_method_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("payment_method_catalog.id"), nullable=False, index=True)
    available_at_pos: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<CompanyPaymentMethodPreference company={self.company_id} method={self.payment_method_id}>"
