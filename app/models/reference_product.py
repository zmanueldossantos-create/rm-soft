"""
Catálogo de referência (SUPER_ADMIN): the products most shops of a sector sell - same name, same barcode, about the
same price - kept once for the whole platform. A new company takes them at its creation (a snapshot: later changes of
the catalog never touch a company that exists), an existing one can pick some. Not a company's product: it holds the
product's fiscal nature (NOR / RED / ISE and its motive), never a company's rate - each company's own rates and regime
decide the VAT when the product is taken.
"""
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ReferenceProduct(Base):
    __tablename__ = "reference_products"
    __table_args__ = (
        # one product per barcode; a product without barcode (bread, by the kilo) is known by its name
        Index("uq_reference_products_barcode", "barcode", unique=True, postgresql_where=text("barcode IS NOT NULL")),
        Index("uq_reference_products_name_no_barcode", text("lower(name)"), unique=True,
              postgresql_where=text("barcode IS NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str | None] = mapped_column(String(150), nullable=True)  # its name: each company gets its own
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_of_measure_catalog.id"), nullable=False)
    tax_category: Mapped[str] = mapped_column(String(3), nullable=False)  # NOR | RED | ISE - the nature, not a rate
    exemption_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_codes.id"), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # indicative; none: the shop sets it
    sectors: Mapped[list[str]] = mapped_column(ARRAY(String(20)), nullable=False, default=list)  # COMERCIO, BAR...
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    units: Mapped[list["ReferenceProductUnit"]] = relationship(
        back_populates="product", cascade="all, delete-orphan", order_by="ReferenceProductUnit.factor", lazy="selectin")


class ReferenceProductUnit(Base):
    """A sale unit of a reference product: a box of 6, a tray of 30 - with its own barcode and price, both optional."""
    __tablename__ = "reference_product_units"
    __table_args__ = (UniqueConstraint("reference_product_id", "unit_of_measure_id", name="uq_reference_product_unit"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    reference_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("reference_products.id", ondelete="CASCADE"), nullable=False, index=True)
    unit_of_measure_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_of_measure_catalog.id"), nullable=False)
    factor: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)  # base units in one of this unit
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True)
    price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)

    product: Mapped[ReferenceProduct] = relationship(back_populates="units")
