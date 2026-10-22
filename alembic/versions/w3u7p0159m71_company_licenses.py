"""company_licenses: the licence files imported on a client's server (LICENSE_REQUIRED)

Revision ID: w3u7p0159m71
Revises: v2t6o9048l60
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "w3u7p0159m71"
down_revision = "v2t6o9048l60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_licenses",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("imported_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("imported_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_company_licenses_company_id", "company_licenses", ["company_id"])
    op.create_index("uq_company_license_current", "company_licenses", ["company_id"], unique=True,
                    postgresql_where=sa.text("is_current"))


def downgrade() -> None:
    op.drop_index("uq_company_license_current", table_name="company_licenses")
    op.drop_index("ix_company_licenses_company_id", table_name="company_licenses")
    op.drop_table("company_licenses")
