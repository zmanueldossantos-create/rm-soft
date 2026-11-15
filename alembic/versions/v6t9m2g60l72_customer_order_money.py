"""Encomendas, step 2: an order's Fatura (FT with a deposit, or FR at the delivery), its credit note when cancelled
after it, and what was done with the deposit (DEVOLVIDO / RETIDO).

Revision ID: v6t9m2g60l72
Revises: u5s8l1f59k71
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v6t9m2g60l72"
down_revision = "u5s8l1f59k71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customer_orders", sa.Column("invoice_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True))
    op.add_column("customer_orders", sa.Column("credit_note_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True))
    op.add_column("customer_orders", sa.Column("deposit_outcome", sa.String(12), nullable=True))


def downgrade() -> None:
    op.drop_column("customer_orders", "deposit_outcome")
    op.drop_column("customer_orders", "credit_note_id")
    op.drop_column("customer_orders", "invoice_id")
