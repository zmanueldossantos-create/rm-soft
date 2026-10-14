"""stock: inventories of a warehouse - expected, counted, difference, validated into adjustments

Revision ID: t9w6x1y50j82
Revises: s8v5w0x49i71
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "t9w6x1y50j82"
down_revision = "s8v5w0x49i71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("RASCUNHO", "VALIDADO", name="inventorystatus")
    op.create_table(
        "stock_inventories",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), sa.ForeignKey("fiscal_periods.id"), nullable=False),
        sa.Column("series", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("validated_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
    )
    for column in ("company_id", "warehouse_id", "fiscal_period_id"):
        op.create_index(f"ix_stock_inventories_{column}", "stock_inventories", [column])
    op.create_table(
        "stock_inventory_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("inventory_id", UUID(as_uuid=True), sa.ForeignKey("stock_inventories.id"), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("counted_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("count_detail", sa.String(200), nullable=True),
        sa.Column("expected_quantity", sa.Numeric(14, 3), nullable=True),
        sa.Column("difference", sa.Numeric(14, 3), nullable=True),
        sa.Column("unit_cost", sa.Numeric(14, 4), nullable=True),
        sa.Column("difference_value", sa.Numeric(16, 2), nullable=True),
    )
    op.create_index("ix_stock_inventory_lines_inventory_id", "stock_inventory_lines", ["inventory_id"])


def downgrade() -> None:
    op.drop_index("ix_stock_inventory_lines_inventory_id", table_name="stock_inventory_lines")
    op.drop_table("stock_inventory_lines")
    for column in ("company_id", "warehouse_id", "fiscal_period_id"):
        op.drop_index(f"ix_stock_inventories_{column}", table_name="stock_inventories")
    op.drop_table("stock_inventories")
    sa.Enum(name="inventorystatus").drop(op.get_bind(), checkfirst=True)
