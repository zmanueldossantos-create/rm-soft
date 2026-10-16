"""supplier payments (PAG): what the company pays its suppliers, allocated to their invoices - the conta corrente

Revision ID: c2f5a0149s71
Revises: b1e4f9038r60
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "c2f5a0149s71"
down_revision = "b1e4f9038r60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("REGISTADO", "ANULADO", name="supplierpaymentstatus")
    op.create_table(
        "supplier_payments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False, index=True),
        sa.Column("series", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("payment_date", sa.Date, nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method_id", UUID(as_uuid=True), sa.ForeignKey("payment_method_catalog.id"), nullable=False),
        sa.Column("bank_account_id", UUID(as_uuid=True), sa.ForeignKey("company_bank_accounts.id"), nullable=True),
        sa.Column("pos_id", UUID(as_uuid=True), sa.ForeignKey("points_of_sale.id"), nullable=True),
        sa.Column("cash_movement_id", UUID(as_uuid=True), sa.ForeignKey("cash_movements.id"), nullable=True),
        sa.Column("reversal_movement_id", UUID(as_uuid=True), sa.ForeignKey("cash_movements.id"), nullable=True),
        sa.Column("reference", sa.String(60), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("status", status, nullable=False),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "series", "number", name="uq_supplier_payment_number"),
    )
    op.create_table(
        "supplier_payment_allocations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("payment_id", UUID(as_uuid=True), sa.ForeignKey("supplier_payments.id"), nullable=False, index=True),
        sa.Column("purchase_invoice_id", UUID(as_uuid=True), sa.ForeignKey("purchase_invoices.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("supplier_payment_allocations")
    op.drop_table("supplier_payments")
    sa.Enum(name="supplierpaymentstatus").drop(op.get_bind(), checkfirst=True)
