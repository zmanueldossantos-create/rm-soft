"""invoice lines invoiced from a guia de remessa: the GR each line comes from (SAF-T OrderReferences)

Revision ID: a0d3e8f27q59
Revises: z5c2d7e16p48
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "a0d3e8f27q59"
down_revision = "z5c2d7e16p48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("goods_movement_id", UUID(as_uuid=True),
                                             sa.ForeignKey("goods_movements.id"), nullable=True))
    op.create_index("ix_invoice_lines_goods_movement_id", "invoice_lines", ["goods_movement_id"])


def downgrade() -> None:
    op.drop_index("ix_invoice_lines_goods_movement_id", table_name="invoice_lines")
    op.drop_column("invoice_lines", "goods_movement_id")
