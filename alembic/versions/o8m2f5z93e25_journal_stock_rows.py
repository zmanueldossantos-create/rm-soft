"""Contabilidade - which stock rows each entry of the day's stock carries: a row written later for a day already posted
(a sale with an earlier date, the rest of a day posted early in Modo formação) gets an entry of its own.

The entries already made: their rows are those of their warehouse and day written before the entry.

Revision ID: o8m2f5z93e25
Revises: n7l1e4y82d14
"""
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "o8m2f5z93e25"
down_revision = "n7l1e4y82d14"
branch_labels = None
depends_on = None

STOCK_DAY_NAMESPACE = uuid.UUID("6f1d5a52-3c1e-4e43-9d7a-5b0f6f0a2c11")  # accounting_integration_service


def upgrade() -> None:
    op.create_table(
        "journal_stock_rows",
        sa.Column("stock_movement_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("stock_movements.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("entry_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("journal_entries.id", ondelete="CASCADE"), nullable=False),
    )
    op.create_index("ix_journal_stock_rows_entry_id", "journal_stock_rows", ["entry_id"])

    bind = op.get_bind()
    entries = {row.source_id: (row.id, row.created_at) for row in bind.execute(sa.text(
        "SELECT id, source_id, created_at FROM journal_entries WHERE source_kind = 'STOCK_DAY' AND source_id IS NOT NULL"))}
    if not entries:
        return
    from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
    code = "CASE " + " ".join(f"WHEN i.invoice_type::text = '{kind}' THEN '{label}'"
                              for kind, label in DOC_CODE_BY_INVOICE_TYPE.items()) + " ELSE '' END"
    rows = bind.execute(sa.text(f"""
        SELECT m.id, m.company_id, m.warehouse_id, m.created_at,
               COALESCE(i.business_date, date(timezone('Africa/Luanda', m.created_at))) AS day
        FROM stock_movements m
        LEFT JOIN invoices i ON i.company_id = m.company_id
             AND m.reference = concat({code}, ' ', i.series, '/', i.number)
        WHERE m.company_id IN (SELECT DISTINCT company_id FROM journal_entries WHERE source_kind = 'STOCK_DAY')
    """)).all()
    links = []
    for row in rows:
        key = uuid.uuid5(STOCK_DAY_NAMESPACE, f"{row.company_id}:{row.warehouse_id}:{row.day.isoformat()}")
        entry = entries.get(key)
        if entry is not None and row.created_at <= entry[1]:
            links.append({"stock_movement_id": row.id, "entry_id": entry[0]})
    if links:
        bind.execute(sa.text("INSERT INTO journal_stock_rows (stock_movement_id, entry_id) VALUES (:stock_movement_id, :entry_id)"
                             " ON CONFLICT DO NOTHING"), links)


def downgrade() -> None:
    op.drop_index("ix_journal_stock_rows_entry_id", table_name="journal_stock_rows")
    op.drop_table("journal_stock_rows")
