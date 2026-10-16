"""
Lots et péremption (point 4) - the stock of a product followed by lot (managed_by_batch) and/or expiry date
(managed_by_expiry), per warehouse.

- StockLot: one lot of one product in one warehouse - its number, its expiry date, the quantity still there (base
  units). The same number and date received again add to the same row. A transfer carries the lot to the destination
  warehouse (a row of its own there, same number and date).
- Stock.quantity stays THE total every screen reads: for a followed product the lots of a warehouse always add up to
  it (or to zero while a warehouse allowing negative stock is below zero - the next entry first fills that gap).
- StockMovementLot: which lots a ledger row (StockMovement) took or filled, and how much - the traceability of a lot.
  The ledger row keeps its total quantity, so every report built on the ledger is unchanged.
"""
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Date, DateTime, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class StockLot(Base):
    __tablename__ = "stock_lots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    # None for a product followed by expiry only; both None = "Sem lote" (stock that came back without a known lot).
    lot_number: Mapped[str | None] = mapped_column(String(60), nullable=True)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)  # base units, never negative
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<StockLot {self.lot_number} {self.expiry_date} qty={self.quantity}>"


class StockMovementLot(Base):
    __tablename__ = "stock_movement_lots"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    movement_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_movements.id", ondelete="CASCADE"), nullable=False, index=True)
    lot_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_lots.id"), nullable=False, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False)  # base units, positive (the ledger row has the direction)

    # relationships only to order the inserts of one flush (the ledger row and a new lot before this row)
    movement = relationship("StockMovement")
    lot = relationship("StockLot")
