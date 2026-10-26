"""customer_display_settings, customer_display_images (Ecrã do cliente, option ECRA_CLIENTE)

Revision ID: c9a3v6715s37
Revises: b8z2u5604r26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c9a3v6715s37"
down_revision = "b8z2u5604r26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_display_settings",
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id"), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("welcome_message", sa.String(200), nullable=True),
        sa.Column("slide_seconds", sa.Integer(), nullable=False, server_default="8"),
    )
    op.create_index("ix_customer_display_settings_company_id", "customer_display_settings", ["company_id"])
    op.create_table(
        "customer_display_images",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("activity_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("activities.id"), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_customer_display_images_company_id", "customer_display_images", ["company_id"])
    op.create_index("ix_customer_display_images_activity_id", "customer_display_images", ["activity_id"])


def downgrade() -> None:
    op.drop_index("ix_customer_display_images_activity_id", table_name="customer_display_images")
    op.drop_index("ix_customer_display_images_company_id", table_name="customer_display_images")
    op.drop_table("customer_display_images")
    op.drop_index("ix_customer_display_settings_company_id", table_name="customer_display_settings")
    op.drop_table("customer_display_settings")
