"""relay_links, relay_requests (the platform's relay of the public API for the companies installed locally)

Revision ID: h4f8a1260x82
Revises: g3e7z0159w71
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h4f8a1260x82"
down_revision = "g3e7z0159w71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "relay_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, unique=True),
        sa.Column("secret_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("secret_prefix", sa.String(16), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("keys", postgresql.JSONB(), nullable=False, server_default="[]"),
        sa.Column("snapshot", postgresql.JSONB(), nullable=True),
        sa.Column("snapshot_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_table(
        "relay_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("key_name", sa.String(100), nullable=False),
        sa.Column("method", sa.String(8), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("query", sa.String(1000), nullable=True),
        sa.Column("body", postgresql.JSONB(), nullable=True),
        sa.Column("idempotency_key", sa.String(100), nullable=True),
        sa.Column("callback_url", sa.String(500), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="PENDENTE"),
        sa.Column("picked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("response_status", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_relay_requests_company_id", "relay_requests", ["company_id"])
    op.create_index("ix_relay_requests_status", "relay_requests", ["status"])
    op.create_index("ix_relay_requests_created_at", "relay_requests", ["created_at"])
    # one request per Idempotency-Key and company: the site's retries are kept once
    op.create_index("uq_relay_requests_idempotency", "relay_requests", ["company_id", "idempotency_key"], unique=True,
                    postgresql_where=sa.text("idempotency_key IS NOT NULL"))


def downgrade() -> None:
    op.drop_index("uq_relay_requests_idempotency", table_name="relay_requests")
    op.drop_index("ix_relay_requests_created_at", table_name="relay_requests")
    op.drop_index("ix_relay_requests_status", table_name="relay_requests")
    op.drop_index("ix_relay_requests_company_id", table_name="relay_requests")
    op.drop_table("relay_requests")
    op.drop_table("relay_links")
