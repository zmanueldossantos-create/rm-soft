"""stock: the history of the cost - the average cost before and after each entry that moved it

Revision ID: q6t3u8v27g59
Revises: p5s2t7u16f48
"""
import sqlalchemy as sa
from alembic import op

revision = "q6t3u8v27g59"
down_revision = "p5s2t7u16f48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_movements", sa.Column("average_cost_before", sa.Numeric(14, 4), nullable=True))
    op.add_column("stock_movements", sa.Column("average_cost_after", sa.Numeric(14, 4), nullable=True))


def downgrade() -> None:
    op.drop_column("stock_movements", "average_cost_after")
    op.drop_column("stock_movements", "average_cost_before")
