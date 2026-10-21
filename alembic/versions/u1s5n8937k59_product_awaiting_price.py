"""products.awaiting_price (taken from the reference catalog without a price: not sold until priced)

Revision ID: u1s5n8937k59
Revises: t0r4m7826j48
"""
import sqlalchemy as sa
from alembic import op

revision = "u1s5n8937k59"
down_revision = "t0r4m7826j48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("awaiting_price", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("products", "awaiting_price")
