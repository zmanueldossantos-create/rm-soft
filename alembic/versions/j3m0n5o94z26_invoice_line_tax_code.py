"""invoice lines: tax_code_snapshot (NOR, RED, INT, ISE, OUT) copied from the VAT rate's category when issued

Lines issued before get the code the SAF-T export used to guess from the rate (0 -> ISE, under 10 -> RED, else NOR):
their past exports stay identical. This one-off backfill is the only place that rule is still applied.

Revision ID: j3m0n5o94z26
Revises: i2l9m4n83y15
"""
from alembic import op
import sqlalchemy as sa

revision = "j3m0n5o94z26"
down_revision = "i2l9m4n83y15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("tax_code_snapshot", sa.String(3), nullable=True))
    op.execute(
        "UPDATE invoice_lines SET tax_code_snapshot = CASE WHEN vat_rate_snapshot <= 0 THEN 'ISE' "
        "WHEN vat_rate_snapshot < 10 THEN 'RED' ELSE 'NOR' END"
    )


def downgrade() -> None:
    op.drop_column("invoice_lines", "tax_code_snapshot")
