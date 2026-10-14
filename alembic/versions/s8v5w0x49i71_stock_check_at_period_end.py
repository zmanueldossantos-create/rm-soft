"""stock: a late exit uses the stock at the end of its own period (option of the company)

Revision ID: s8v5w0x49i71
Revises: r7u4v9w38h60
"""
import sqlalchemy as sa
from alembic import op

revision = "s8v5w0x49i71"
down_revision = "r7u4v9w38h60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("stock_check_at_period_end", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("companies", "stock_check_at_period_end")
