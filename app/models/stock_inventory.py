"""
StockInventory / StockInventoryLine - an inventory of one warehouse (Inventário, point 11): the stock the system
expects of each product, the quantity counted on the shelves, and the difference, valued at the average cost.

A draft (RASCUNHO) is filled in and saved as often as needed; its expected quantities are always the live ones. Its
validation (VALIDADO) books an adjustment (AJUSTE, reference = the inventory's number) for every counted line that
differs, and freezes each line's expected quantity, difference and value - the document never changes afterwards.
A line left uncounted changes nothing. Booked in a period like every internal entry (the active one, or the
soft-closed one for an inventory of the month just ended) - see stock_inventory_service.
"""
import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class InventoryStatus(str, enum.Enum):
    RASCUNHO = "RASCUNHO"
    VALIDADO = "VALIDADO"


class StockInventory(Base):
    __tablename__ = "stock_inventories"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    fiscal_period_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("fiscal_periods.id"), nullable=False, index=True)
    series: Mapped[str] = mapped_column(String(20), nullable=False)  # INV2026
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[InventoryStatus] = mapped_column(Enum(InventoryStatus), nullable=False, default=InventoryStatus.RASCUNHO)
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)
    created_by_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    validated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class StockInventoryLine(Base):
    __tablename__ = "stock_inventory_lines"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    inventory_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("stock_inventories.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False)
    # in the base unit; None = not counted (nothing changes for this product)
    counted_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    count_detail: Mapped[str | None] = mapped_column(String(200), nullable=True)  # "1 SC + 17 KG", as counted
    # frozen at the validation (a draft shows the live expected stock)
    expected_quantity: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    difference: Mapped[float | None] = mapped_column(Numeric(14, 3), nullable=True)
    unit_cost: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    difference_value: Mapped[float | None] = mapped_column(Numeric(16, 2), nullable=True)
