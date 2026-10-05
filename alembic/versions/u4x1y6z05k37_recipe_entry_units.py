"""recipes in units: an ingredient and a yield keep what was typed (1 SC, 2 CX) beside their base quantity, the only
reference for stock and cost - existing recipes keep their base quantities and show them as such

Revision ID: u4x1y6z05k37
Revises: t3w0x5y94j26
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "u4x1y6z05k37"
down_revision = "t3w0x5y94j26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("recipe_ingredients", sa.Column("entry_quantity", sa.Numeric(14, 4), nullable=True))
    op.add_column("recipe_ingredients", sa.Column("entry_sale_unit_id", UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True))
    op.add_column("products", sa.Column("batch_yield_entry", sa.Numeric(14, 4), nullable=True))
    op.add_column("products", sa.Column("batch_yield_sale_unit_id", UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("products", "batch_yield_sale_unit_id")
    op.drop_column("products", "batch_yield_entry")
    op.drop_column("recipe_ingredients", "entry_sale_unit_id")
    op.drop_column("recipe_ingredients", "entry_quantity")
