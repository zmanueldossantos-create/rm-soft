"""notification_settings, notification_recipients, notification_outbox (Notificações, option NOTIFICACOES)

Revision ID: b8z2u5604r26
Revises: a7y1t4593q15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b8z2u5604r26"
down_revision = "a7y1t4593q15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "notification_settings",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("include_gestor_actions", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("sale_min_amount", sa.Numeric(14, 2), nullable=True),
    )
    op.create_table(
        "notification_recipients",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("address", sa.String(160), nullable=True),
        sa.Column("telegram_name", sa.String(150), nullable=True),
        sa.Column("link_code", sa.String(12), nullable=True, unique=True),
        sa.Column("events", postgresql.ARRAY(sa.String(20)), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notification_recipients_company_id", "notification_recipients", ["company_id"])
    op.create_table(
        "notification_outbox",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("recipient_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("notification_recipients.id", ondelete="SET NULL"), nullable=True),
        sa.Column("recipient_name", sa.String(100), nullable=False),
        sa.Column("event", sa.String(20), nullable=False),
        sa.Column("channel", sa.String(10), nullable=False),
        sa.Column("address", sa.String(160), nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("text", sa.String(2000), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDENTE"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_notification_outbox_company_id", "notification_outbox", ["company_id"])
    op.create_index("ix_notification_outbox_next_attempt_at", "notification_outbox", ["next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_notification_outbox_next_attempt_at", table_name="notification_outbox")
    op.drop_index("ix_notification_outbox_company_id", table_name="notification_outbox")
    op.drop_table("notification_outbox")
    op.drop_index("ix_notification_recipients_company_id", table_name="notification_recipients")
    op.drop_table("notification_recipients")
    op.drop_table("notification_settings")
