"""Reservas - the supplements of a passage: an excess at its exit (charged, or let go with a reason) or a
prolongation bought while there - each with its document.

Revision ID: s3q6j9d37i69
Revises: r2p5i8c26h58
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s3q6j9d37i69"
down_revision = "r2p5i8c26h58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "booking_supplements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("booking_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("bookings.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("slices", sa.Integer(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=True),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("waived_reason", sa.String(255), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_booking_supplements_company_id", "booking_supplements", ["company_id"])
    op.create_index("ix_booking_supplements_booking_id", "booking_supplements", ["booking_id"])


def downgrade() -> None:
    op.drop_index("ix_booking_supplements_booking_id", table_name="booking_supplements")
    op.drop_index("ix_booking_supplements_company_id", table_name="booking_supplements")
    op.drop_table("booking_supplements")
