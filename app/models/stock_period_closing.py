"""
StockPeriodClosing - the stock of a product in a warehouse, frozen when a fiscal period is closed for good (Fecho de
stock por período, an option of the company: Company.stock_period_closing). One row per product and warehouse:
the stock at the start of the period, what came in and went out, the stock at its end, and its value at the average
cost of that time. Written once by stock_period_closing_service.freeze_period_stock, never changed afterwards: what
the accountant saw at the close stays what it was, whatever happens later.
"""
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class StockPeriodClosing(Base):
    __tablename__ = "stock_period_closings"
    __table_args__ = (
        UniqueConstraint("fiscal_period_id", "product_id", "warehouse_id", name="uq_stock_period_closing"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False)
    opening_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    in_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    out_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    closing_quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)  # None = cost unknown
    closing_value: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
