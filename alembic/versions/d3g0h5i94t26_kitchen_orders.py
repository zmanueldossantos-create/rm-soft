"""cuisine : kitchen_orders (envois en cuisine) et etat cuisine des lignes de compte

Revision ID: d3g0h5i94t26
Revises: c2f9g4h83s15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "d3g0h5i94t26"
down_revision = "c2f9g4h83s15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "kitchen_orders",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("account_id", UUID(as_uuid=True), sa.ForeignKey("open_accounts.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("sent_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "day", "number", name="uq_kitchen_orders_company_day_number"),
    )
    op.create_index("ix_kitchen_orders_company_id", "kitchen_orders", ["company_id"])
    op.create_index("ix_kitchen_orders_account_id", "kitchen_orders", ["account_id"])
    op.add_column("open_account_lines", sa.Column("kitchen_status", sa.String(20), nullable=True))
    op.add_column("open_account_lines", sa.Column("kitchen_order_id", UUID(as_uuid=True), nullable=True))
    op.add_column("open_account_lines", sa.Column("kitchen_modified", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("open_account_lines", sa.Column("cancel_reason", sa.String(255), nullable=True))
    op.add_column("open_account_lines", sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_open_account_lines_kitchen_order_id", "open_account_lines", "kitchen_orders",
                          ["kitchen_order_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_open_account_lines_kitchen_order_id", "open_account_lines", type_="foreignkey")
    for column in ("cancelled_at", "cancel_reason", "kitchen_modified", "kitchen_order_id", "kitchen_status"):
        op.drop_column("open_account_lines", column)
    op.drop_index("ix_kitchen_orders_account_id", table_name="kitchen_orders")
    op.drop_index("ix_kitchen_orders_company_id", table_name="kitchen_orders")
    op.drop_table("kitchen_orders")
