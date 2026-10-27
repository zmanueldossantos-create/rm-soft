"""relay_agent_settings (the client's server: where its relay agent connects)

Revision ID: i5g9b2371y93
Revises: h4f8a1260x82
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i5g9b2371y93"
down_revision = "h4f8a1260x82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relay_agent_settings",
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), primary_key=True),
        sa.Column("relay_url", sa.String(300), nullable=False),
        sa.Column("secret_encrypted", sa.String(500), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_ok_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(300), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("requests_done", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("relay_agent_settings")
