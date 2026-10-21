"""company backups: the settings (automatic / manual) and the copies made

Revision ID: s9q3l6715i37
Revises: r8p2k5604h26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "s9q3l6715i37"
down_revision = "r8p2k5604h26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_backup_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("mode", sa.String(10), nullable=False),
        sa.Column("times", postgresql.ARRAY(sa.String(5)), nullable=False),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_company_backup_settings_company_id", "company_backup_settings", ["company_id"], unique=True)
    op.create_index("ix_company_backup_settings_next_run_at", "company_backup_settings", ["next_run_at"])
    op.create_table(
        "company_backups",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("file_name", sa.String(200), nullable=True),
        sa.Column("size_bytes", sa.BigInteger(), nullable=True),
        sa.Column("error", sa.String(500), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_company_backups_company_id", "company_backups", ["company_id"])
    op.create_index("ix_company_backups_created_at", "company_backups", ["created_at"])


def downgrade() -> None:
    op.drop_table("company_backups")
    op.drop_table("company_backup_settings")
