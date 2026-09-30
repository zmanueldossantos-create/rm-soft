"""
Product model - core product sheet.
See specification v6/v7, section 5.1 (Code, Price, Minimum threshold, DLC)
and 5.4 (barcode), 5.5 (sold by weight).
Multi-unit conversions (section 5.3) and warehouse stock (section 5.2) are
separate models added later, both referencing this Product.
product_type (BEM/SERVICO) maps directly to SAF-T ProductType (P/S) -
services (e.g. hotel room nights, labour) need distinct handling from
physical goods for the SAF-T export (see saf_t_generator.py). Since
Video 3, actual sellable services live in their own Service model - this
enum stays on Product mainly for historical/SAF-T-export reasons.

unit_of_measure_id and batch_yield support production/transformation (see
RecipeIngredient, stock_service.produce_stock) - a recipe is expressed
per BATCH rather than per single unit (e.g. "1 saco de farinha + 1 saco
de fermento -> 400 paes"), matching how a baker actually thinks and
avoiding error-prone tiny decimals. batch_yield only matters for products
that have a recipe; it defaults to 1 (a "batch" of one unit) for all
other products, so it's harmless everywhere else.

Extended (Video 3) with: image, category, brand, richer status, the
managed-by-lote/stock/validade toggles, POS/return availability, and a
separate purchase price alongside the existing sale price.
"""
import enum
import uuid
from datetime import date, datetime

from sqlalchemy import String, Numeric, Boolean, Date, DateTime, ForeignKey, Enum, func, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base
from app.models.service import ProductServiceStatus


class ProductType(str, enum.Enum):
    BEM = "BEM"          # physical good - SAF-T ProductType "P"
    SERVICO = "SERVICO"  # service - SAF-T ProductType "S"


class Product(Base):
    """
    A sellable product, scoped to a Company (tenant).
    code is the internal reference (unique per company); barcode is the
    optional EAN/UPC for scanning at the register (section 5.4).
    """
    __tablename__ = "products"
    __table_args__ = (
        UniqueConstraint("company_id", "code", name="uq_product_company_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    # A raw material (is_raw_material) carries no VAT rate: it is never sold. Every other product
    # must have one - enforced by product_service._check_vat_rule.
    vat_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_rates.id"), nullable=True)
    # Required whenever the selected VAT rate is 0% (isento) - AGT/SAF-T
    # legally requires a justification code (the official 28-code catalog,
    # see VatCode / Configuracoes) for every exempt line.
    exemption_reason_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vat_codes.id"), nullable=True)
    category_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_categories.id"), nullable=True)
    code: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[str | None] = mapped_column(String(100), nullable=True)  # marca
    image_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    barcode: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    price: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)  # preco de venda
    purchase_price: Mapped[float | None] = mapped_column(Numeric(12, 2), nullable=True)  # preco de compra
    min_stock_threshold: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=0)
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)  # DLC
    product_type: Mapped[ProductType] = mapped_column(Enum(ProductType), nullable=False, default=ProductType.BEM)
    # Platform catalog reference (Configuracoes > Unidades) - replaces the
    # old free-text field; existing rows keep their raw text separately
    # (unit_of_measure_legacy) until re-assigned through the UI.
    unit_of_measure_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("unit_of_measure_catalog.id"), nullable=True)
    unit_of_measure_legacy: Mapped[str | None] = mapped_column(String(30), nullable=True)
    # How many units of THIS product one full recipe batch yields (see
    # RecipeIngredient.quantity_per_batch). Irrelevant unless this product
    # has a recipe; default 1 keeps it harmless for every other product.
    batch_yield: Mapped[float] = mapped_column(Numeric(12, 3), nullable=False, default=1)
    # Raw material / production input (e.g. flour, yeast) - never sold
    # directly, never shown in the sellable Produtos catalog or invoice
    # product pickers; managed in its own "Materia-prima" screen and used
    # only as a RecipeIngredient (see discussion on production module).
    is_raw_material: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Management toggles (Video 3)
    managed_by_batch: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # gerido por lotes
    managed_by_stock: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)  # gerido por stocks
    managed_by_expiry: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)  # gerido por validade
    not_available_pos: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # True for items never meant to be sold at all (housekeeping supplies -
    # towels, soap) - excluded from every sales-facing product picker
    # (Caixa, ContasAbertas), but still selectable in Consumo Interno's
    # picker. Distinct from not_available_pos, which only hides an item at
    # the POS specifically while it may still be sold elsewhere (invoices).
    internal_use_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    status: Mapped[ProductServiceStatus] = mapped_column(Enum(ProductServiceStatus, name="productservicestatus"), nullable=False, default=ProductServiceStatus.ACTIVO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<Product {self.code} - {self.name}>"