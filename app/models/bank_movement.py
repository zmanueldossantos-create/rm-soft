"""
BankMovement - a movement of a bank account typed in the Tesouraria (Bancos), the ones no document makes: bank fees,
a capital entry, a tax paid by transfer... Each one takes a reason of the catalog used for the banks (its direction:
entrada or saída). Never deleted: a mistake is cancelled (ANULADO, with its reason) and the statement keeps both lines.
The movements a document makes (a sale or receipt collected on the account, a supplier payment made from it) are read
from those documents - see app.services.bank_treasury_service.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.movement_type import MovementDirection


class BankMovementStatus(str, enum.Enum):
    REGISTADO = "REGISTADO"
    ANULADO = "ANULADO"


class BankMovement(Base):
    __tablename__ = "bank_movements"
    __table_args__ = (UniqueConstraint("company_id", "series", "number", name="uq_bank_movement_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=False, index=True)
    reason_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cash_movement_reasons.id"), nullable=False)
    direction: Mapped[MovementDirection] = mapped_column(Enum(MovementDirection), nullable=False)
    series: Mapped[str] = mapped_column(String(20), nullable=False)  # BCO2026
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    movement_date: Mapped[date] = mapped_column(Date, nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)  # always > 0, the direction says which way
    reference: Mapped[str | None] = mapped_column(String(60), nullable=True)  # the bank's reference, a transfer number
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    status: Mapped[BankMovementStatus] = mapped_column(Enum(BankMovementStatus), nullable=False, default=BankMovementStatus.REGISTADO)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
