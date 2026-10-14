"""purchase invoices: the unit of a product line, the automatic stock entry of the invoice and its reversal

Revision ID: w2z9a4b83m15
Revises: v1y8z3a72l04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "w2z9a4b83m15"
down_revision = "v1y8z3a72l04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_invoice_lines", sa.Column("sale_unit_id", UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True))
    op.add_column("purchase_invoice_lines", sa.Column("unit_snapshot", sa.String(20), nullable=True))
    op.add_column("purchase_invoice_lines", sa.Column("unit_factor", sa.Numeric(14, 4), server_default="1", nullable=False))
    op.add_column("purchase_invoices", sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=True))
    op.add_column("purchase_invoices", sa.Column("stock_entry_document_id", UUID(as_uuid=True), sa.ForeignKey("stock_movement_documents.id"), nullable=True))
    op.add_column("purchase_invoices", sa.Column("stock_exit_document_id", UUID(as_uuid=True), sa.ForeignKey("stock_movement_documents.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("purchase_invoices", "stock_exit_document_id")
    op.drop_column("purchase_invoices", "stock_entry_document_id")
    op.drop_column("purchase_invoices", "warehouse_id")
    op.drop_column("purchase_invoice_lines", "unit_factor")
    op.drop_column("purchase_invoice_lines", "unit_snapshot")
    op.drop_column("purchase_invoice_lines", "sale_unit_id")
