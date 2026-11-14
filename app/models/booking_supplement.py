"""
BookingSupplement - what a passage (a room taken by the hour, paid at its Entrada) adds after it: an excess at its exit
(the guest stayed past the paid time: the started slices of its rate) or a prolongation (more time bought while
there). Each one is either sold at once (invoice_id: an ordinary paid document of the till) or, for an excess only,
let go with the reason said (waived_reason, invoice_id None) - the gestor is told either way. The stay's revenue
(Histórico) is its Entrada's document plus these.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Integer, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base

KIND_EXCESS = "EXCESSO"
KIND_PROLONGATION = "PROLONGAMENTO"


class BookingSupplement(Base):
    __tablename__ = "booking_supplements"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    booking_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("bookings.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # EXCESSO, PROLONGAMENTO
    slices: Mapped[int] = mapped_column(Integer, nullable=False)  # how many times the rate (1 x VIP 1 hora)
    minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # the excess, in minutes (EXCESSO)
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("invoices.id"), nullable=True)
    waived_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)  # an excess not charged: why
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
