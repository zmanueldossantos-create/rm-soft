"""Tesouraria - a transfer between two banks still em trânsito 2 days after it left is reported to the gestor once.

Revision ID: d7b0u4o82t14
Revises: c6a9t3n71s03
"""
import sqlalchemy as sa
from alembic import op

revision = "d7b0u4o82t14"
down_revision = "c6a9t3n71s03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bank_transfers", sa.Column("stale_notified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bank_transfers", "stale_notified_at")
