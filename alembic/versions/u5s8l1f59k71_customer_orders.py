"""Encomendas (capability ORDERS): customer orders made and handed over later - delivery date and mode, lines with a
production note, status ENCOMENDADA -> EM_PRODUCAO -> PRONTA -> ENTREGUE or CANCELADA; numbered ENC<year>/n.

Revision ID: u5s8l1f59k71
Revises: t4r7k0e48j70
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "u5s8l1f59k71"
down_revision = "t4r7k0e48j70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("ENCOMENDADA", "EM_PRODUCAO", "PRONTA", "ENTREGUE", "CANCELADA", name="customer_order_status")
    op.create_table(
        "customer_orders",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False),
        sa.Column("contact_name", sa.String(120), nullable=True),
        sa.Column("contact_phone", sa.String(20), nullable=True),
        sa.Column("delivery_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivery_mode", sa.String(10), nullable=False, server_default="LOJA"),
        sa.Column("delivery_address", sa.String(300), nullable=True),
        sa.Column("notes", sa.String(1000), nullable=True),
        sa.Column("status", status, nullable=False, server_default="ENCOMENDADA"),
        sa.Column("cancel_reason", sa.String(255), nullable=True),
        sa.Column("status_changed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "year", "number", name="uq_customer_orders_number"),
    )
    op.create_index("ix_customer_orders_company_id", "customer_orders", ["company_id"])
    op.create_index("ix_customer_orders_customer_id", "customer_orders", ["customer_id"])
    op.create_index("ix_customer_orders_delivery_at", "customer_orders", ["delivery_at"])
    op.create_table(
        "customer_order_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customer_orders.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(12, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False, server_default="0"),
        sa.Column("production_note", sa.String(500), nullable=True),
    )
    op.create_index("ix_customer_order_lines_company_id", "customer_order_lines", ["company_id"])
    op.create_index("ix_customer_order_lines_order_id", "customer_order_lines", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_order_lines_order_id", table_name="customer_order_lines")
    op.drop_index("ix_customer_order_lines_company_id", table_name="customer_order_lines")
    op.drop_table("customer_order_lines")
    op.drop_index("ix_customer_orders_delivery_at", table_name="customer_orders")
    op.drop_index("ix_customer_orders_customer_id", table_name="customer_orders")
    op.drop_index("ix_customer_orders_company_id", table_name="customer_orders")
    op.drop_table("customer_orders")
    sa.Enum(name="customer_order_status").drop(op.get_bind(), checkfirst=True)
