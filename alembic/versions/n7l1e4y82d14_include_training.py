"""Contabilidade - a company in Modo formação may have its documents in the accounting (a demonstration, a training).

Revision ID: n7l1e4y82d14
Revises: m6k0d3x71c03
"""
import sqlalchemy as sa
from alembic import op

revision = "n7l1e4y82d14"
down_revision = "m6k0d3x71c03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounting_settings", sa.Column("include_training", sa.Boolean(), nullable=False, server_default="false"))


def downgrade() -> None:
    op.drop_column("accounting_settings", "include_training")
