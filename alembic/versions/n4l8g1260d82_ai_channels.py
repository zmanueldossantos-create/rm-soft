"""AI assistant on Telegram (and later WhatsApp): the bot, the linked chats, the linking codes

Revision ID: n4l8g1260d82
Revises: m3k7f0159c71
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "n4l8g1260d82"
down_revision = "m3k7f0159c71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("telegram_bot_token_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column("telegram_bot_username", sa.String(100), nullable=True))
    op.add_column("platform_settings", sa.Column("telegram_webhook_secret", sa.String(64), nullable=True))
    op.create_table(
        "ai_channel_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("external_id", sa.String(64), nullable=False),
        sa.Column("external_name", sa.String(150), nullable=True),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_conversations.id"), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("linked_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_ai_channel_links_company_id", "ai_channel_links", ["company_id"])
    op.create_index("ix_ai_channel_links_user_id", "ai_channel_links", ["user_id"])
    op.create_index("ix_ai_channel_links_external_id", "ai_channel_links", ["external_id"])
    op.create_table(
        "ai_link_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("channel", sa.String(20), nullable=False),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_link_codes_user_id", "ai_link_codes", ["user_id"])
    op.create_index("ix_ai_link_codes_code", "ai_link_codes", ["code"])


def downgrade() -> None:
    op.drop_table("ai_link_codes")
    op.drop_table("ai_channel_links")
    for column in ("telegram_webhook_secret", "telegram_bot_username", "telegram_bot_token_encrypted"):
        op.drop_column("platform_settings", column)
