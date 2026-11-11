"""Reservas - a rate of a resource type may have hours of its own (Pernoite 22:00 -> 07:30, Day use 08:00 -> 18:00):
the booking takes them and the rate is charged once per period.

Revision ID: p9n3g6a04f36
Revises: o8m2f5z93e25
"""
import sqlalchemy as sa
from alembic import op

revision = "p9n3g6a04f36"
down_revision = "o8m2f5z93e25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("stay_start_time", sa.Time(), nullable=True))
    op.add_column("services", sa.Column("stay_end_time", sa.Time(), nullable=True))


def downgrade() -> None:
    op.drop_column("services", "stay_end_time")
    op.drop_column("services", "stay_start_time")
