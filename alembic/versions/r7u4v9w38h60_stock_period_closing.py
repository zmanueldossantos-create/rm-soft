"""stock: the stock frozen at the close of a fiscal period (option of the company)

Revision ID: r7u4v9w38h60
Revises: q6t3u8v27g59
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "r7u4v9w38h60"
down_revision = "q6t3u8v27g59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("stock_period_closing", sa.Boolean(), server_default="false", nullable=False))
    op.create_table(
        "stock_period_closings",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), sa.ForeignKey("fiscal_periods.id"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("opening_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("in_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("out_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("closing_quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("closing_value", sa.Numeric(16, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("fiscal_period_id", "product_id", "warehouse_id", name="uq_stock_period_closing"),
    )
    op.create_index("ix_stock_period_closings_company_id", "stock_period_closings", ["company_id"])
    op.create_index("ix_stock_period_closings_fiscal_period_id", "stock_period_closings", ["fiscal_period_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_period_closings_fiscal_period_id", table_name="stock_period_closings")
    op.drop_index("ix_stock_period_closings_company_id", table_name="stock_period_closings")
    op.drop_table("stock_period_closings")
    op.drop_column("companies", "stock_period_closing")
