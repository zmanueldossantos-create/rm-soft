"""Contingência (Faturação Eletrónica): the company's state of its link to the AGT (automatic or manual contingência,
network failures, last answer) and the 18 h alert of a late document.

Revision ID: o1m5f8937e59
Revises: n0l4e7826d48
"""
import sqlalchemy as sa
from alembic import op

revision = "o1m5f8937e59"
down_revision = "n0l4e7826d48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("agt_contingency", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("companies", sa.Column("agt_contingency_manual", sa.Boolean(), nullable=False, server_default="false"))
    op.add_column("companies", sa.Column("agt_contingency_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("companies", sa.Column("agt_net_failures", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("companies", sa.Column("agt_first_failure_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("companies", sa.Column("agt_last_ok_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("agt_late_notified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "agt_late_notified_at")
    for column in ("agt_last_ok_at", "agt_first_failure_at", "agt_net_failures", "agt_contingency_since",
                   "agt_contingency_manual", "agt_contingency"):
        op.drop_column("companies", column)
