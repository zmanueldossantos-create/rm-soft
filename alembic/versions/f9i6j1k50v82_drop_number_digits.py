"""activities and invoices: number_digits dropped - always 3, copied to every invoice, read by no screen and not by
the SAF-T generator (numbering goes through document_series)

Revision ID: f9i6j1k50v82
Revises: e8h5i0j49u71
"""
from alembic import op
import sqlalchemy as sa

revision = "f9i6j1k50v82"
down_revision = "e8h5i0j49u71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("invoices", "number_digits")
    op.drop_column("activities", "number_digits")


def downgrade() -> None:
    op.add_column("activities", sa.Column("number_digits", sa.Integer(), nullable=False, server_default="3"))
    op.add_column("invoices", sa.Column("number_digits", sa.Integer(), nullable=False, server_default="3"))
