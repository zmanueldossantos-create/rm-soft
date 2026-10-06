"""
OpenAccountLine model - one item accumulated on an OpenAccount before it is
settled. Mirrors InvoiceLine's snapshot pattern (name/price captured at add
time, so later product/service edits never retroactively change what a
customer already ordered) but stays deliberately simpler - no VAT/discount
math here, since that is all recomputed properly by invoice_service at
close_account time, the same way pos_service.checkout already does for a
normal Caixa sale.
"""
import uuid
from datetime import datetime

from sqlalchemy import String, Numeric, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class OpenAccountLine(Base):
    __tablename__ = "open_account_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    account_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("open_accounts.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=True)
    service_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("services.id"), nullable=True)

    name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False)
    unit_price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)

    # The unit the line is sold in, as in the till cart: the base unit (no sale unit, factor 1) or one of the
    # product's sale units (a CX of 24 at its own price). The stock counts quantity x unit_factor.
    sale_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_sale_units.id"), nullable=True)
    unit_factor: Mapped[float] = mapped_column(Numeric(12, 4), nullable=False, default=1, server_default="1")
    unit_code_snapshot: Mapped[str | None] = mapped_column(String(10), nullable=True)

    added_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<OpenAccountLine {self.name_snapshot} x{self.quantity}>"
