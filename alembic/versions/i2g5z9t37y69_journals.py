"""Contabilidade - the journals (diários) and their entries (lançamentos); the default journals for the companies whose
chart of accounts is already started.

Revision ID: i2g5z9t37y69
Revises: h1f4y8s26x58
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "i2g5z9t37y69"
down_revision = "h1f4y8s26x58"
branch_labels = None
depends_on = None

DEFAULT_JOURNALS = (("VND", "Vendas"), ("CMP", "Compras"), ("CX", "Caixa"), ("BCO", "Bancos"),
                    ("OD", "Operações diversas"), ("ABE", "Abertura"))


def upgrade() -> None:
    journals = op.create_table(
        "journals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("code", sa.String(10), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "code", name="uq_journal_company_code"),
    )
    op.create_table(
        "journal_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("journal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journals.id"), nullable=False, index=True),
        sa.Column("entry_date", sa.Date(), nullable=False, index=True),
        sa.Column("description", sa.String(200), nullable=False),
        sa.Column("document_ref", sa.String(60), nullable=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="RASCUNHO"),
        sa.Column("year", sa.Integer(), nullable=True),
        sa.Column("number", sa.Integer(), nullable=True),
        sa.Column("reversal_of_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_entries.id"), nullable=True, unique=True),
        sa.Column("created_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("posted_by", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("journal_id", "year", "number", name="uq_journal_entry_number"),
        sa.CheckConstraint("status IN ('RASCUNHO', 'LANCADO')", name="ck_journal_entry_status"),
    )
    op.create_table(
        "journal_entry_lines",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("journal_entries.id", ondelete="CASCADE"),
                  nullable=False, index=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("debit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.Column("credit", sa.Numeric(18, 2), nullable=False, server_default="0"),
        sa.CheckConstraint("debit >= 0 AND credit >= 0 AND (debit = 0 OR credit = 0)", name="ck_journal_line_one_side"),
    )
    # the companies whose chart is already started get the default journals now (the others when they start it)
    companies = op.get_bind().execute(sa.text(
        "SELECT company_id FROM accounting_settings WHERE chart_source IS NOT NULL")).scalars().all()
    rows = [{"id": uuid.uuid4(), "company_id": cid, "code": code, "name": name, "is_active": True}
            for cid in companies for code, name in DEFAULT_JOURNALS]
    if rows:
        op.bulk_insert(journals, rows)


def downgrade() -> None:
    op.drop_table("journal_entry_lines")
    op.drop_table("journal_entries")
    op.drop_table("journals")
