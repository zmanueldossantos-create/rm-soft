"""Reservas - every change of a stay's exit recorded (the end before and after): the Histórico shows the life of each
occupation (entry, prolongations, excess, exit), not only its first document.

Revision ID: t4r7k0e48j70
Revises: s3q6j9d37i69
"""
import sqlalchemy as sa
from alembic import op

revision = "t4r7k0e48j70"
down_revision = "s3q6j9d37i69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booking_supplements", sa.Column("ends_before", sa.DateTime(timezone=True), nullable=True))
    op.add_column("booking_supplements", sa.Column("ends_after", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("booking_supplements", "ends_after")
    op.drop_column("booking_supplements", "ends_before")
