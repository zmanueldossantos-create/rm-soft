"""stock: a period is closed for good only after the inventory of every warehouse holding stock (company option)

Revision ID: u0x7y2z61k93
Revises: t9w6x1y50j82
"""
import sqlalchemy as sa
from alembic import op

revision = "u0x7y2z61k93"
down_revision = "t9w6x1y50j82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("inventory_before_close", sa.Boolean(), server_default="false", nullable=False))


def downgrade() -> None:
    op.drop_column("companies", "inventory_before_close")
