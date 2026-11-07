"""Contabilidade - the account of each treasury reason (motivo de tesouraria), the other side of the till or bank in
the system's entries.

Revision ID: l5j9c2w60b92
Revises: k4i8b1v59a81
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "l5j9c2w60b92"
down_revision = "k4i8b1v59a81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cash_movement_reasons", sa.Column(
        "account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("cash_movement_reasons", "account_id")
