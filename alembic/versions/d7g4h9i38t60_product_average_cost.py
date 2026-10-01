"""products: weighted average cost (CMP), initialised from the purchase price when there is one

Revision ID: d7g4h9i38t60
Revises: c6f3g8h27s59
"""
from alembic import op
import sqlalchemy as sa

revision = "d7g4h9i38t60"
down_revision = "c6f3g8h27s59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("average_cost", sa.Numeric(14, 4), nullable=True))
    op.execute("UPDATE products SET average_cost = purchase_price WHERE purchase_price > 0")


def downgrade() -> None:
    op.drop_column("products", "average_cost")
