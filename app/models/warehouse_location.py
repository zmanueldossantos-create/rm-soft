"""
Emplacements (point 5, option A) - where the goods are put away inside a warehouse (a shelf, an aisle, a fridge).

- WarehouseLocation: one place of one warehouse - its code (A-01, Prateleira 3; 30 characters, the length the SAF-T
  gives a LocationID) and an optional description. Optional: a warehouse without any keeps working as before.
- ProductLocation: where a product is usually kept in a warehouse - one place per product and warehouse.
The quantities stay counted per warehouse (and lot): a location tells where to put away and where to look.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class WarehouseLocation(Base):
    __tablename__ = "warehouse_locations"
    __table_args__ = (UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ProductLocation(Base):
    __tablename__ = "product_locations"
    __table_args__ = (UniqueConstraint("product_id", "warehouse_id", name="uq_product_location_warehouse"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    warehouse_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouses.id"), nullable=False, index=True)
    location_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("warehouse_locations.id"), nullable=False, index=True)
