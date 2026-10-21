"""support sessions (the platform's support access to a company)

Revision ID: q7o1j4593g15
Revises: p6n0i3482f04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "q7o1j4593g15"
down_revision = "p6n0i3482f04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "support_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("admin_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("code_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("code_used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_support_sessions_company_id", "support_sessions", ["company_id"])


def downgrade() -> None:
    op.drop_index("ix_support_sessions_company_id", table_name="support_sessions")
    op.drop_table("support_sessions")
