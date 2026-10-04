"""company_fiscal_regimes: the history of each company's fiscal regimes, each with the day it took effect - existing
companies start with their current regime from their creation day

Revision ID: q0t7u2v61g93
Revises: p9s6t1u50f82
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "q0t7u2v61g93"
down_revision = "p9s6t1u50f82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "company_fiscal_regimes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("fiscal_regime_id", UUID(as_uuid=True), sa.ForeignKey("fiscal_regimes.id"), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO company_fiscal_regimes (id, company_id, fiscal_regime_id, valid_from) "
        "SELECT gen_random_uuid(), id, fiscal_regime_id, created_at::date FROM companies WHERE fiscal_regime_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_table("company_fiscal_regimes")
