"""
Activity model - a business line / point of sale within a Company.
See discussion on multi-activity companies: a single company (one NIF) can
run several activities (e.g. Hotel, Padaria, Bar, Restaurante) - confirmed
in a real support conversation with Kiami (an AGT-certified vendor): the
SAF-T export aggregates all activities' invoices under the same file, but
each activity typically uses its own invoice series (e.g. "PAD", "BAR").

Company-scoped (not a separate tenant) - Products remain company-wide for
now; only Invoice numbering is activity-scoped via series_code.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Activity(Base):
    __tablename__ = "activities"
    __table_args__ = (
        UniqueConstraint("company_id", "series_code", name="uq_activity_company_series_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # Which catalog Module this activity represents - the company must have
    # been granted this module (see CompanyModule) before GESTOR can create it.
    module_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("modules.id"), nullable=False, index=True)
    # This activity's own point-of-sale warehouse - stock is received
    # centrally (see Warehouse "Armazem Principal") and internally
    # transferred here before being sold under this activity. Auto-created
    # alongside the Activity - see activity_service.create_activity.
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # e.g. "Padaria", "Bar Central"
    # Short uppercase code used as the SAF-T invoice series (InvoiceNo = "{type} {series}/{number}").
    series_code: Mapped[str] = mapped_column(String(10), nullable=False)
    # How many digits the sequential number is zero-padded to (e.g. 3 -> "001").
    # Snapshotted onto each Invoice at creation time so past documents never
    # reformat retroactively if this setting changes later.
    number_digits: Mapped[int] = mapped_column(nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Activity {self.name} ({self.series_code})>"
