"""
OpenAccountTransfer - insert-only audit trail of every move of lines between open
accounts (table transfer, bill split). Rows are never updated or deleted: moving items
between tabs is a classic place for restaurant fraud, so who moved what, from which
account to which, and when must stay answerable forever.

name/quantity/unit_price are snapshots of what moved. For a full-line move the line
keeps its id (target_line_id == source_line_id); for a partial move the target line is
a new row copied from the source (see open_account_service.transfer_lines).
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OpenAccountTransfer(Base):
    __tablename__ = "open_account_transfers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    source_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_accounts.id"), nullable=False, index=True)
    target_account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_accounts.id"), nullable=False, index=True)
    source_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_account_lines.id"), nullable=False)
    target_line_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_account_lines.id"), nullable=False)

    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    moved_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    moved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<OpenAccountTransfer {self.name_snapshot} x{self.quantity} {self.source_account_id} -> {self.target_account_id}>"
