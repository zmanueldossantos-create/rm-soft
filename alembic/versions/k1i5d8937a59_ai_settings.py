"""AI assistant settings: the platform's provider, model, key and limit; the per-company switches

Revision ID: k1i5d8937a59
Revises: j9h4c7826z48
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "k1i5d8937a59"
down_revision = "j9h4c7826z48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("ai_provider", sa.String(20), nullable=True))
    op.add_column("platform_settings", sa.Column("ai_model", sa.String(100), nullable=True))
    op.add_column("platform_settings", sa.Column("ai_api_key_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column("ai_monthly_limit", sa.Integer(), server_default="300", nullable=False))
    op.create_table(
        "company_ai_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, unique=True),
        sa.Column("ai_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("whatsapp_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("telegram_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("email_enabled", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("monthly_limit", sa.Integer(), nullable=True),
        sa.Column("confirm_documents", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("confirm_sends", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("company_ai_settings")
    for column in ("ai_monthly_limit", "ai_api_key_encrypted", "ai_model", "ai_provider"):
        op.drop_column("platform_settings", column)
