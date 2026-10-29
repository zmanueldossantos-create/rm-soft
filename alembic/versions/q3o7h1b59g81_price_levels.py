"""Preço 1 / 2 / 3: a product and each of its sale units may carry two more prices the seller chooses from (permission
invoices:price_levels); a document line keeps the level it was sold at.

Revision ID: q3o7h1b59g81
Revises: p2n6g0a48f70
"""
import sqlalchemy as sa
from alembic import op

revision = "q3o7h1b59g81"
down_revision = "p2n6g0a48f70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("products", "product_sale_units"):
        op.add_column(table, sa.Column("price_2", sa.Numeric(12, 2), nullable=True))
        op.add_column(table, sa.Column("price_3", sa.Numeric(12, 2), nullable=True))
    op.add_column("invoice_lines", sa.Column("price_level", sa.Integer(), server_default="1", nullable=False))


def downgrade() -> None:
    op.drop_column("invoice_lines", "price_level")
    for table in ("product_sale_units", "products"):
        op.drop_column(table, "price_3")
        op.drop_column(table, "price_2")
