"""
BankTransfer - money moved between two bank accounts of the company (Tesouraria › Bancos).

  - same bank (both accounts at the BAI, say): the money is on the other account at once - DISPONIVEL on its date;
  - two banks (BAI -> BFA): it leaves the first account on its date and stays EM_TRANSITO (on the way, in no account)
    until someone confirms «Fundos disponíveis» with the day the second bank shows it (usually the next working day);
    only then it enters the second account.
Never deleted: a mistake is cancelled (ANULADO, with its reason) - the statements keep the transfer and its reversal.
Both accounts in the same currency (no exchange here).
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, Numeric, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class BankTransferStatus(str, enum.Enum):
    EM_TRANSITO = "EM_TRANSITO"  # left the first account, not yet on the second
    DISPONIVEL = "DISPONIVEL"  # on the second account
    ANULADO = "ANULADO"


class BankTransfer(Base):
    __tablename__ = "bank_transfers"
    __table_args__ = (UniqueConstraint("company_id", "series", "number", name="uq_bank_transfer_number"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(20), nullable=False)  # TRF2026
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    from_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=False, index=True)
    to_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=False, index=True)
    amount: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False)
    transfer_date: Mapped[date] = mapped_column(Date, nullable=False)  # it leaves the first account
    available_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # it is on the second account
    status: Mapped[BankTransferStatus] = mapped_column(Enum(BankTransferStatus), nullable=False)
    reference: Mapped[str | None] = mapped_column(String(60), nullable=True)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    confirmed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    cancel_reason: Mapped[str | None] = mapped_column(String(300), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    # the gestor was told it is still em trânsito STALE_DAYS after it left (once - see bank_transfer_service.check_stale)
    stale_notified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
