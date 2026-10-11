"""bookings: the invoice of a prepaid passage, and the real departure of every stay

Revision ID: n3q0r5s94d26
Revises: m2p9q4r83c15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "n3q0r5s94d26"
down_revision = "m2p9q4r83c15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("bookings_invoice_id_fkey", "bookings", "invoices", ["invoice_id"], ["id"])
    op.add_column("bookings", sa.Column("checked_out_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("bookings", "checked_out_at")
    op.drop_constraint("bookings_invoice_id_fkey", "bookings", type_="foreignkey")
    op.drop_column("bookings", "invoice_id")
