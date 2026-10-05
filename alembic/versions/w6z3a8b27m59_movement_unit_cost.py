"""stock_movements.unit_cost: the cost per base unit of a movement - what a production consumed at its average cost,
and what it made at the cost of that consumption (None = cost incomplete)

Revision ID: w6z3a8b27m59
Revises: v5y2z7a16l48
"""
from alembic import op
import sqlalchemy as sa

revision = "w6z3a8b27m59"
down_revision = "v5y2z7a16l48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_movements", sa.Column("unit_cost", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_movements", "unit_cost")
