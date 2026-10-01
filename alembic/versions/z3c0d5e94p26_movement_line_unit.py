"""movement document lines entered in a product unit: sale_unit_id + unit_factor (stock moves quantity x factor)

Revision ID: z3c0d5e94p26
Revises: y2b9c4d83o15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z3c0d5e94p26"
down_revision = "y2b9c4d83o15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stock_movement_document_lines", sa.Column("sale_unit_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True))
    op.add_column("stock_movement_document_lines", sa.Column("unit_factor", sa.Numeric(14, 4), nullable=False, server_default="1"))


def downgrade() -> None:
    op.drop_column("stock_movement_document_lines", "unit_factor")
    op.drop_column("stock_movement_document_lines", "sale_unit_id")
