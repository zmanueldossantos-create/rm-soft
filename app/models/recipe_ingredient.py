"""
RecipeIngredient model - Bill of Materials (nomenclature) for a finished
product. Generic and extensible - not specific to bread: any product
(bread, gelado, sandwich, etc.) can have a recipe defining which
ingredients (other products) it consumes and in what quantity, used to
transform raw materials into a finished good (see stock_service.produce_stock
and discussion on production/transformation).
Company-wide, like the products themselves - a recipe is a property of
the finished product, not of any one activity.
"""
import uuid
from datetime import datetime

from sqlalchemy import Numeric, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.dialects.postgresql import UUID

from app.core.database import Base


class RecipeIngredient(Base):
    __tablename__ = "recipe_ingredients"
    __table_args__ = (
        UniqueConstraint("finished_product_id", "ingredient_product_id", name="uq_recipe_ingredient"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    company_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("companies.id"), nullable=False, index=True)
    finished_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    ingredient_product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("products.id"), nullable=False, index=True)
    # How much of the ingredient is consumed by ONE FULL BATCH of the recipe
    # (see Product.batch_yield - a batch yields several units of the
    # finished product, not just one) - matches how production actually
    # gets measured (e.g. "1 saco de farinha per batch"), not tiny decimals.
    quantity_per_batch: Mapped[float] = mapped_column(Numeric(14, 4), nullable=False)
    # What the user typed (1 SC): quantity_per_batch above is that in base units (20 KG), the only reference
    # for stock and cost; these two only show the recipe the way it was thought.
    entry_quantity: Mapped[float | None] = mapped_column(Numeric(14, 4), nullable=True)
    entry_sale_unit_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("product_sale_units.id"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<RecipeIngredient {self.finished_product_id} needs {self.quantity_per_unit}x {self.ingredient_product_id}>"
