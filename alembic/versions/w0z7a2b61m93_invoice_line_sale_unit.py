"""invoice lines sold in a sale unit: sale_unit_id, unit code and factor snapshots (stock moves quantity x factor)

Revision ID: w0z7a2b61m93
Revises: v9y6z1a50l82
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "w0z7a2b61m93"
down_revision = "v9y6z1a50l82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("sale_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True))
    op.add_column("invoice_lines", sa.Column("unit_code_snapshot", sa.String(10), nullable=True))
    op.add_column("invoice_lines", sa.Column("unit_factor", sa.Numeric(14, 4), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("invoice_lines", "unit_factor")
    op.drop_column("invoice_lines", "unit_code_snapshot")
    op.drop_column("invoice_lines", "sale_unit_id")
