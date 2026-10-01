"""movement documents: total_quantity dropped - it added different units (kilos and eggs) and was never shown

Revision ID: e8h5i0j49u71
Revises: d7g4h9i38t60
"""
from alembic import op
import sqlalchemy as sa

revision = "e8h5i0j49u71"
down_revision = "d7g4h9i38t60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("stock_movement_documents", "total_quantity")


def downgrade() -> None:
    op.add_column("stock_movement_documents", sa.Column("total_quantity", sa.Numeric(14, 3), nullable=False, server_default="0"))
