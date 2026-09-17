"""
CustomerBankAccountLink - links a Customer to one of the COMPANY's own
bank accounts (Video 2: "Contas Bancarias / Documentos Vendas" tab) -
this is NOT the customer's own bank account, it is which of the
company's accounts should be shown/used on sales documents for this
specific customer.
"""
import uuid
from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID
from app.core.database import Base


class CustomerBankAccountLink(Base):
    __tablename__ = "customer_bank_account_links"
    __table_args__ = (
        UniqueConstraint("customer_id", "company_bank_account_id", name="uq_customer_bank_account_link"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False, index=True)
    company_bank_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company_bank_accounts.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<CustomerBankAccountLink {self.customer_id}>"
