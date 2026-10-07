"""
ResourceTypeCatalog model - the managed catalog of resource types (Chambre,
Praticien, Mesa, Cadeira...) a company can create Resources under, replacing
the earlier free-text resource_type field on Resource (which allowed
inconsistent casing/spelling - "CHAMBRE" vs "Chambre" vs "chambre" would have
silently created distinct, un-mergeable types). Company-scoped since
different businesses want different vocabularies.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ResourceTypeCatalog(Base):
    __tablename__ = "resource_type_catalog"
    __table_args__ = (
        UniqueConstraint("company_id", "name", name="uq_resource_type_company_name"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    # If true, a Booking against a Resource of this type must have a Service
    # selected (e.g. CHAMBRE - a room always has a rate to charge, even for a
    # short 30min/1h stay) - see booking_service.create_booking's validation.
    # Types where billing happens entirely through OpenAccount extras instead
    # (e.g. MESA - a table has no fixed booking-time rate) leave this false.
    requires_service: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<ResourceTypeCatalog {self.name}>"

# Case-insensitive uniqueness (migration h1k8l3m72x04): no duplicate whatever the case. Declared here too, so a
# database built from the models (tests, new installs) has the same protection as a migrated one.
from sqlalchemy import Index as _Index, func as _func  # noqa: E402

_Index("uq_resource_types_company_name_ci", ResourceTypeCatalog.company_id, _func.lower(ResourceTypeCatalog.name), unique=True)
