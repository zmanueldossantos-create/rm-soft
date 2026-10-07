"""
Stock model - current quantity of a Product within a Warehouse.
See specification v6/v7, section 5.2. One row per (product, warehouse) pair,
updated by StockMovement entries - never written to directly by business
logic, always through stock_service functions that also log a movement.
"""
import uuid
from datetime import datetime

from sqlalchemy import Numeric, DateTime, ForeignKey, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class Stock(Base):
    __tablename__ = "stock"
    __table_args__ = (
        UniqueConstraint("product_id", "warehouse_id", name="uq_stock_product_warehouse"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)

    quantity: Mapped[float] = mapped_column(Numeric(14, 3), nullable=False, default=0)

    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Stock product={self.product_id} qty={self.quantity}>"
