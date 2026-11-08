"""Contabilidade - the stock in the accounting: the inventory system of the company (permanente by default) and the
account of each stock movement type.

Revision ID: m6k0d3x71c03
Revises: l5j9c2w60b92
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "m6k0d3x71c03"
down_revision = "l5j9c2w60b92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounting_settings", sa.Column("inventory_system", sa.String(12), nullable=False, server_default="PERMANENTE"))
    op.create_table(
        "stock_type_accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("movement_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("movement_types.id"), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.UniqueConstraint("company_id", "movement_type_id", name="uq_stock_type_account"),
    )


def downgrade() -> None:
    op.drop_table("stock_type_accounts")
    op.drop_column("accounting_settings", "inventory_system")
