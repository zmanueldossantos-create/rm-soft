"""invoices.agt_next_attempt_at / agt_attempts: the AGT queue kept in the database (AGT_QUEUE=base, Windows setup)

Revision ID: x4v8q1260n82
Revises: w3u7p0159m71
"""
import sqlalchemy as sa
from alembic import op

revision = "x4v8q1260n82"
down_revision = "w3u7p0159m71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("agt_next_attempt_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("agt_attempts", sa.Integer(), nullable=False, server_default="0"))
    op.create_index("ix_invoices_agt_next_attempt_at", "invoices", ["agt_next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_invoices_agt_next_attempt_at", table_name="invoices")
    op.drop_column("invoices", "agt_attempts")
    op.drop_column("invoices", "agt_next_attempt_at")
