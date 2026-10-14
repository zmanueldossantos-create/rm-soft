"""purchase invoices for the SAF-T: the supplier document's type (NC refers to its invoice), its printed hash, the
destination of the deductible VAT per line

Revision ID: y4b1c6d05o37
Revises: x3a0b5c94n26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "y4b1c6d05o37"
down_revision = "x3a0b5c94n26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("purchase_invoices", sa.Column("purchase_type", sa.String(2), server_default="FT", nullable=False))
    op.add_column("purchase_invoices", sa.Column("supplier_hash", sa.String(4), nullable=True))
    op.add_column("purchase_invoices", sa.Column("reference_invoice_id", UUID(as_uuid=True), sa.ForeignKey("purchase_invoices.id"), nullable=True))
    op.add_column("purchase_invoice_lines", sa.Column("deductible_tax_type", sa.String(4), server_default="OBC", nullable=False))
    # the existing lines: a product is inventory, a service a service, the rest other consumables
    op.execute("UPDATE purchase_invoice_lines SET deductible_tax_type = 'INV' WHERE product_id IS NOT NULL")
    op.execute("UPDATE purchase_invoice_lines SET deductible_tax_type = 'SERV' WHERE service_id IS NOT NULL")


def downgrade() -> None:
    op.drop_column("purchase_invoice_lines", "deductible_tax_type")
    op.drop_column("purchase_invoices", "reference_invoice_id")
    op.drop_column("purchase_invoices", "supplier_hash")
    op.drop_column("purchase_invoices", "purchase_type")
