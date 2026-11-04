"""
CompanyBankAccount - one bank account for a Company (Video 1, onglet 3:
Coordenadas Bancarias). A company can have any number of these; the tab
itself is optional, but once a row is started every field on it is
required (enforced at service layer).
"""
import uuid
from datetime import date, datetime
from sqlalchemy import String, Boolean, Date, DateTime, ForeignKey, Numeric, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CompanyBankAccount(Base):
    __tablename__ = "company_bank_accounts"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    bank_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("banks.id"), nullable=False)
    account_number: Mapped[str] = mapped_column(String(50), nullable=False)
    # Displayed with the "AO06" country/check-digit prefix and dot-grouped
    # every 4 characters in the UI - stored here as the raw digits.
    iban: Mapped[str] = mapped_column(String(34), nullable=False)
    currency_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("currencies.id"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Tesouraria: the balance on the bank's statement on the day the company starts following the account here - the
    # movements before that day are not counted (they are in this balance). None: counted from the first movement.
    opening_balance: Mapped[float] = mapped_column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    opening_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CompanyBankAccount {self.account_number}>"
