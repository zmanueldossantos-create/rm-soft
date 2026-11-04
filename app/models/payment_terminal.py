"""
PaymentTerminal - a card terminal (TPA) or a Multicaixa Express number of the company, and the bank account its
payments land on. A payment by card at the till says nothing about the bank: the terminal does. A company may have
several terminals, on the same bank or on different ones.

  - payment_method_ids: the payment methods it receives (the ones that land on a bank account: cartão, Express...).
    A till payment with one of them goes to this terminal's bank.
  - pos_id: the point of sale it sits at; None = any point of sale of the company (a terminal carried around).
  - the funds land on the account the same day (TPA and Express alike): the bank statement shows them on the sale's day.
Never deleted once used: deactivated (is_active), the documents keep pointing at it.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class TerminalKind(str, enum.Enum):
    TPA = "TPA"  # a card terminal of a bank
    EXPRESS = "EXPRESS"  # a Multicaixa Express number


class PaymentTerminal(Base):
    __tablename__ = "payment_terminals"
    __table_args__ = (UniqueConstraint("company_id", "name", name="uq_payment_terminal_name"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(60), nullable=False)  # "TPA BAI Balcão", "Express 923..."
    kind: Mapped[TerminalKind] = mapped_column(Enum(TerminalKind), nullable=False)
    bank_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=False, index=True)
    pos_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("points_of_sale.id"), nullable=True)
    payment_method_ids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)), nullable=False, default=list)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<PaymentTerminal {self.name}>"
