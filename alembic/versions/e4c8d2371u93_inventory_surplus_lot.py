"""inventory surplus lot

A product followed by lot / expiry counted above what was expected: the lot its surplus enters.

Revision ID: e4c8d2371u93
Revises: d3a6b1250t82
"""
import sqlalchemy as sa
from alembic import op

revision = "e4c8d2371u93"
down_revision = "d3a6b1250t82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_inventory_lines", sa.Column("surplus_lot_number", sa.String(60), nullable=True))
    op.add_column("stock_inventory_lines", sa.Column("surplus_expiry_date", sa.Date, nullable=True))


def downgrade() -> None:
    op.drop_column("stock_inventory_lines", "surplus_expiry_date")
    op.drop_column("stock_inventory_lines", "surplus_lot_number")
