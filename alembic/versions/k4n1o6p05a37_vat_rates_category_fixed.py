"""vat_rates: categories fixed - rates created without one got NOR by default (0 % and 5 % too); now that invoice
lines copy the category as their SAF-T tax code, a 0 % rate must be ISE and a 5 % rate RED

Revision ID: k4n1o6p05a37
Revises: j3m0n5o94z26
"""
from alembic import op

revision = "k4n1o6p05a37"
down_revision = "j3m0n5o94z26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE vat_rates SET tax_category = 'ISE' WHERE rate = 0 AND tax_category = 'NOR'")
    op.execute("UPDATE vat_rates SET tax_category = 'RED' WHERE rate = 5 AND tax_category = 'NOR'")
    op.alter_column("vat_rates", "tax_category", server_default=None)


def downgrade() -> None:
    pass
