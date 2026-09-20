"""add invoice_lines retention snapshot (name, rate, amount)

Like vat_rate_snapshot: what was withheld on a line must survive later changes of the withholding
catalog. Three nullable columns - nothing is dropped and no row is deleted. The upgrade checks the
columns first, so running it on a database that already has them is harmless.

Backfill, only where it is unambiguous: a single-line invoice whose only line is a service whose
current withholding tax has exactly the rate deduced from the stored numbers
(retention_total / line_subtotal). Every other invoice is left empty rather than guessed.

Revision ID: i5e2d8b31c07
Revises: h4d1c7a90e3b6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'i5e2d8b31c07'
down_revision: Union[str, None] = 'h4d1c7a90e3b6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('invoice_lines')}
    if 'retention_name_snapshot' not in existing:
        op.add_column('invoice_lines', sa.Column('retention_name_snapshot', sa.String(length=150), nullable=True))
    if 'retention_rate' not in existing:
        op.add_column('invoice_lines', sa.Column('retention_rate', sa.Numeric(5, 2), nullable=True))
    if 'retention_amount' not in existing:
        op.add_column('invoice_lines', sa.Column('retention_amount', sa.Numeric(14, 2), nullable=True))

    bind.execute(sa.text("""
        UPDATE invoice_lines AS l
        SET retention_amount = i.retention_total,
            retention_rate = ROUND(i.retention_total / l.line_subtotal * 100, 2),
            retention_name_snapshot = wt.name
        FROM invoices AS i, services AS s, withholding_taxes AS wt
        WHERE i.id = l.invoice_id
          AND s.id = l.service_id
          AND wt.id = s.withholding_tax_id
          AND l.retention_amount IS NULL
          AND i.retention_total > 0
          AND l.line_subtotal > 0
          AND (SELECT count(*) FROM invoice_lines AS x WHERE x.invoice_id = i.id) = 1
          AND ROUND(i.retention_total / l.line_subtotal * 100, 2) = wt.rate
    """))


def downgrade() -> None:
    # Fiscal snapshot data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("invoice_lines retention snapshot columns are never dropped by a downgrade")