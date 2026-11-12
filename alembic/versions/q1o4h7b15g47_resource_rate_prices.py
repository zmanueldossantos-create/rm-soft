"""Recursos - a resource may have its own price for a rate of its type (the Luanda room's 1 hora at 8 000 where the
type says 5 000).

Revision ID: q1o4h7b15g47
Revises: p9n3g6a04f36
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "q1o4h7b15g47"
down_revision = "p9n3g6a04f36"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "resource_rate_prices",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("resource_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("resources.id", ondelete="CASCADE"), nullable=False),
        sa.Column("service_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("services.id", ondelete="CASCADE"), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.UniqueConstraint("resource_id", "service_id", name="uq_resource_rate_price"),
    )
    op.create_index("ix_resource_rate_prices_company_id", "resource_rate_prices", ["company_id"])
    op.create_index("ix_resource_rate_prices_resource_id", "resource_rate_prices", ["resource_id"])


def downgrade() -> None:
    op.drop_index("ix_resource_rate_prices_resource_id", table_name="resource_rate_prices")
    op.drop_index("ix_resource_rate_prices_company_id", table_name="resource_rate_prices")
    op.drop_table("resource_rate_prices")
