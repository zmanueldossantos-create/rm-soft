"""
Resource model - a generic bookable "thing" belonging to an Activity: a hotel
room, a spa therapist, a hairdresser's chair, a restaurant table, a dentist's
chair. This is the shared foundation behind the Booking model - see that
model's docstring for how reservations attach to a Resource.

resource_type_id references the managed ResourceTypeCatalog (Chambre,
Praticien, Mesa...) instead of a free-text string - see that model's
docstring for why (consistent naming, no silent duplicate-type creation
from casing/spelling variants). capacity is optional (e.g. a table seats 4,
a single-person massage room doesn't need one).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Boolean, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Resource(Base):
    __tablename__ = "resources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    resource_type_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resource_type_catalog.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    capacity: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Resource {self.resource_type_id} {self.name}>"
