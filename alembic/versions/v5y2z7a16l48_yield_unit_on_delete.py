"""products.batch_yield_sale_unit_id: ON DELETE SET NULL - products and their packages point at each other; a package is
never deleted (only deactivated), the yield itself stays in base units, so losing the link only loses its display

Revision ID: v5y2z7a16l48
Revises: u4x1y6z05k37
"""
from alembic import op

revision = "v5y2z7a16l48"
down_revision = "u4x1y6z05k37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("products_batch_yield_sale_unit_id_fkey", "products", type_="foreignkey")
    op.create_foreign_key("products_batch_yield_sale_unit_id_fkey", "products", "product_sale_units",
                          ["batch_yield_sale_unit_id"], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    op.drop_constraint("products_batch_yield_sale_unit_id_fkey", "products", type_="foreignkey")
    op.create_foreign_key("products_batch_yield_sale_unit_id_fkey", "products", "product_sale_units",
                          ["batch_yield_sale_unit_id"], ["id"])
