"""
KitchenOrder - one sending of an open account's dishes to the kitchen (point 34b): who sent it, when, and the short
number of the day (#12) the kitchen calls it by. Its lines are the OpenAccountLines that point to it.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Integer, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class KitchenOrder(Base):
    __tablename__ = "kitchen_orders"
    __table_args__ = (UniqueConstraint("company_id", "day", "number", name="uq_kitchen_orders_company_day_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_accounts.id"), nullable=False, index=True)
    day: Mapped[date] = mapped_column(Date, nullable=False)
    number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3... per company and per day
    sent_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<KitchenOrder #{self.number} {self.day}>"
