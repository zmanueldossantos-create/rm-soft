"""Contabilidade - the entries made by the system from the documents: the document of an entry, the documents waiting
for theirs (pending_integrations), and the day the integration starts from (the chart's start day for the companies
whose chart is already started).

Revision ID: j3h7a0u48z70
Revises: i2g5z9t37y69
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "j3h7a0u48z70"
down_revision = "i2g5z9t37y69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("journal_entries", sa.Column("source_kind", sa.String(20), nullable=True))
    op.add_column("journal_entries", sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_index("ix_journal_entries_source_id", "journal_entries", ["source_id"])
    op.create_unique_constraint("uq_journal_entry_source", "journal_entries", ["company_id", "source_kind", "source_id"])
    op.add_column("accounting_settings", sa.Column("integration_start", sa.Date(), nullable=True))
    op.execute("UPDATE accounting_settings SET integration_start = (chart_started_at AT TIME ZONE 'Africa/Luanda')::date "
               "WHERE chart_started_at IS NOT NULL")
    op.create_table(
        "pending_integrations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document", sa.String(60), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(300), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "source_kind", "source_id", name="uq_pending_integration_source"),
    )


def downgrade() -> None:
    op.drop_table("pending_integrations")
    op.drop_column("accounting_settings", "integration_start")
    op.drop_constraint("uq_journal_entry_source", "journal_entries", type_="unique")
    op.drop_index("ix_journal_entries_source_id", "journal_entries")
    op.drop_column("journal_entries", "source_id")
    op.drop_column("journal_entries", "source_kind")
