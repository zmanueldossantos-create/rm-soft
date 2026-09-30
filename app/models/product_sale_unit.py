"""
ProductSaleUnit - another way to sell a product than its base unit (section 5.3, multi-unit conversions): a pallet of
30 eggs, a box of 3 blisters. The product itself stays the base unit (its unit_of_measure_id, price and stock); a sale
unit holds how many base units it contains (factor), its own price and optionally its own barcode. Stock always moves in
base units: selling 1 pallet takes factor = 30 eggs out. Never deleted, only deactivated.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class ProductSaleUnit(Base):
    __tablename__ = "product_sale_units"
    __table_args__ = (UniqueConstraint("product_id", "unit_of_measure_id", name="uq_product_sale_unit"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_of_measure_catalog.id"), nullable=False)
    factor: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)  # base units contained in one sale unit
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
