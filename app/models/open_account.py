"""
OpenAccount model - a running tab that accumulates consumption over time
before being settled in a single final sale: a Bar customer's tab, a
Restaurant table's bill during the meal, a Hotel guest's room extras
(mini-bar, room service) until check-out. This is the second generic
building block of the sector road-map, alongside Resource/Booking (which
handles advance reservations - a different concern: OpenAccount has no
notion of a reserved time slot, just an accumulating balance).

label is a free-form display name (e.g. "Mesa 4", "Quarto 101", "Joao -
tab") since the vocabulary differs per sector. resource_id optionally ties
the account to a Resource (a hotel room, a restaurant table) when one
exists - a simple Bar tab may have no Resource at all, just a label.

Closing an account (see open_account_service.close_account) converts its
lines into a real Invoice via the existing pos_service.checkout /
invoice_service.create_invoice pipeline - OpenAccount itself never touches
stock or tax calculation directly, it only accumulates the pending lines
until that conversion happens.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import String, Enum, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OpenAccountStatus(str, enum.Enum):
    ABERTA = "ABERTA"
    FECHADA = "FECHADA"


class OpenAccount(Base):
    __tablename__ = "open_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    activity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("activities.id"), nullable=False, index=True)
    pos_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=False, index=True)
    resource_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("resources.id"), nullable=True, index=True)
    # Links a hotel stay's running tab back to the Booking that started it (set at
    # check-in) - used for occupancy history/revenue reports. Null for accounts not
    # tied to a reservation (a plain Bar tab, a Restaurant table opened without one).
    booking_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=True, index=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=True)

    label: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[OpenAccountStatus] = mapped_column(Enum(OpenAccountStatus), default=OpenAccountStatus.ABERTA, nullable=False)

    opened_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)

    def __repr__(self) -> str:
        return f"<OpenAccount {self.label} {self.status}>"
