"""api_idempotency (the public API's writes, kept with their answer: an Idempotency-Key sent again creates nothing twice)

Revision ID: f2d6y9048v60
Revises: e1c5x8937u59
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f2d6y9048v60"
down_revision = "e1c5x8937u59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_idempotency",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("api_key_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True),
        sa.Column("idem_key", sa.String(100), nullable=False),
        sa.Column("path", sa.String(300), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("status_code", sa.Integer(), nullable=False),
        sa.Column("response", postgresql.JSONB(), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("company_id", "idem_key", name="uq_api_idempotency_company_key"),
    )
    op.create_index("ix_api_idempotency_created_at", "api_idempotency", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_api_idempotency_created_at", table_name="api_idempotency")
    op.drop_table("api_idempotency")
