"""AI assistant actions (pending confirmation) and the company's email account

Revision ID: m3k7f0159c71
Revises: l2j6e9048b60
"""
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "m3k7f0159c71"
down_revision = "l2j6e9048b60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_email_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, unique=True),
        sa.Column("smtp_host", sa.String(255), nullable=False),
        sa.Column("smtp_port", sa.Integer(), nullable=False),
        sa.Column("security", sa.String(10), nullable=False),
        sa.Column("username", sa.String(255), nullable=True),
        sa.Column("password_encrypted", sa.Text(), nullable=True),
        sa.Column("from_email", sa.String(255), nullable=False),
        sa.Column("from_name", sa.String(150), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "ai_pending_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("conversation_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_conversations.id"), nullable=True),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("summary", postgresql.JSONB(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("result", postgresql.JSONB(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_ai_pending_actions_company_id", "ai_pending_actions", ["company_id"])
    op.create_index("ix_ai_pending_actions_user_id", "ai_pending_actions", ["user_id"])
    op.add_column("ai_messages", sa.Column("action_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("ai_pending_actions.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("ai_messages", "action_id")
    op.drop_table("ai_pending_actions")
    op.drop_table("company_email_settings")
