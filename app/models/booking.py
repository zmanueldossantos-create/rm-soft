"""
Booking model - a reservation of a Resource for a time span, optionally tied
to a Customer and a Service (the prestation being booked, e.g. "Massagem
60min"). This is the generic reservation engine shared across every
appointment-based sector (Hotel, Spa, Salao, Clinica) and, later, Restaurant's
table pre-booking (see the road-map discussion distinguishing this from
OpenAccount, which handles the separate "running tab" need).

Overlap rule: two active (non-CANCELADA) bookings on the SAME resource must
never have overlapping [starts_at, ends_at) ranges - enforced in
booking_service, not at the DB level (a range-overlap constraint isn't
portable across all Postgres versions without extensions), so always go
through booking_service.create_booking rather than inserting directly.

Hotel's multi-night stays reuse starts_at/ends_at unchanged (just spanning
days instead of hours) - see road-map Phase 4 for the extra check-in/check-out
actions layered on top, and OpenAccount for the stay's accumulated extras.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class BookingStatus(str, enum.Enum):
    PENDENTE = "PENDENTE"
    CONFIRMADA = "CONFIRMADA"
    EM_CURSO = "EM_CURSO"
    CONCLUIDA = "CONCLUIDA"
    CANCELADA = "CANCELADA"
    NO_SHOW = "NO_SHOW"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=False, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True, index=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)

    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    status: Mapped[BookingStatus] = mapped_column(Enum(BookingStatus), default=BookingStatus.PENDENTE, nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Free-text guest details, independent of the Customer (fiscal) link: a table booked for
    # "Familia Silva - 6" needs no Customer record, and a hotel can keep "Consumidor Final" as
    # the fiscal customer while still knowing who actually stays.
    guest_name: Mapped[str | None] = mapped_column(String(150), nullable=True)
    party_size: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Booking resource={self.resource_id} {self.starts_at}-{self.ends_at} {self.status}>"
