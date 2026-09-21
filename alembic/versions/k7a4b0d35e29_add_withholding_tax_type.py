"""add withholding_taxes.tax_type and invoice_lines.retention_type (SAF-T WithholdingTax)

The SAF-T (XSD) reports the withholding tax of a document with a mandatory type (IRT, II, IS, IVA, IPU, IAC, OU).
The catalog gets the SAF-T code; the line copies it when the document is issued (like retention_rate), so a later
change of the catalog does not alter an issued document. The AGT e-invoicing API names the property tax "IP" where the
SAF-T says "IPU": convert at that boundary. Additive only: two nullable columns and data filled in where unambiguous
(the 6.5% withholding is the imposto industrial - "II"; the imposto predial is "IPU"). Nothing is deleted.

Revision ID: k7a4b0d35e29
Revises: j6f3a9c24d18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'k7a4b0d35e29'
down_revision: Union[str, None] = 'j6f3a9c24d18'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if 'tax_type' not in {c['name'] for c in inspector.get_columns('withholding_taxes')}:
        op.add_column('withholding_taxes', sa.Column('tax_type', sa.String(length=3), nullable=True))
    if 'retention_type' not in {c['name'] for c in inspector.get_columns('invoice_lines')}:
        op.add_column('invoice_lines', sa.Column('retention_type', sa.String(length=3), nullable=True))

    bind.execute(
        sa.text("UPDATE withholding_taxes SET tax_type = 'II' WHERE tax_type IS NULL AND name ILIKE :pattern"),
        {"pattern": "Reten%fonte%"},
    )
    bind.execute(
        sa.text("UPDATE withholding_taxes SET tax_type = 'IPU' WHERE tax_type IS NULL AND name ILIKE :pattern"),
        {"pattern": "%predial%"},
    )
    # Lines issued before the type existed: complete them from the name copied on the line, when it matches the catalog.
    bind.execute(sa.text("""
        UPDATE invoice_lines AS l
        SET retention_type = wt.tax_type
        FROM withholding_taxes AS wt
        WHERE l.retention_type IS NULL
          AND l.retention_amount IS NOT NULL
          AND wt.name = l.retention_name_snapshot
          AND wt.tax_type IS NOT NULL
    """))


def downgrade() -> None:
    # Fiscal snapshot data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("withholding tax types are never dropped by a downgrade")