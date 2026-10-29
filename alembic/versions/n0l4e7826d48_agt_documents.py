"""Faturação Eletrónica, the documents: the AGT's states VALIDADA / VALIDADA_P, the AGT's receipt and refusal reasons
on the invoice, and the number of each line (backfilled in the order the lines were created).

Revision ID: n0l4e7826d48
Revises: m9k3d6715c37
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "n0l4e7826d48"
down_revision = "m9k3d6715c37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE invoicestatus ADD VALUE IF NOT EXISTS 'VALIDADA'")
    op.execute("ALTER TYPE invoicestatus ADD VALUE IF NOT EXISTS 'VALIDADA_P'")
    op.add_column("invoices", sa.Column("agt_request_id", sa.String(20), nullable=True))
    op.add_column("invoices", sa.Column("agt_errors", postgresql.JSONB(), nullable=True))
    op.add_column("invoices", sa.Column("agt_last_error", sa.String(300), nullable=True))
    op.add_column("invoices", sa.Column("agt_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("agt_validated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoice_lines", sa.Column("line_number", sa.Integer(), nullable=True))
    op.execute("""
        UPDATE invoice_lines l SET line_number = n.rn
        FROM (SELECT id, row_number() OVER (PARTITION BY invoice_id ORDER BY created_at, id) AS rn FROM invoice_lines) n
        WHERE l.id = n.id
    """)


def downgrade() -> None:
    op.drop_column("invoice_lines", "line_number")
    for column in ("agt_validated_at", "agt_sent_at", "agt_last_error", "agt_errors", "agt_request_id"):
        op.drop_column("invoices", column)
    # the enum values VALIDADA / VALIDADA_P stay (PostgreSQL cannot drop an enum value)
