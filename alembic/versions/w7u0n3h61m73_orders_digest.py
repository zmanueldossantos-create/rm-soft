"""Encomendas, step 3: the hour the next day's orders are sent (ENCOMENDAS_AMANHA, 18 h by default) and the last day
they were.

Revision ID: w7u0n3h61m73
Revises: v6t9m2g60l72
"""
import sqlalchemy as sa
from alembic import op

revision = "w7u0n3h61m73"
down_revision = "v6t9m2g60l72"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("notification_settings", sa.Column("orders_digest_hour", sa.Integer(), nullable=False, server_default="18"))
    op.add_column("notification_settings", sa.Column("orders_digest_sent_on", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("notification_settings", "orders_digest_sent_on")
    op.drop_column("notification_settings", "orders_digest_hour")
