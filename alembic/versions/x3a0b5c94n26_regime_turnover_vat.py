"""fiscal regimes: the VAT owed on the turnover (Simplificado 7 %) - the apuramento do IVA

Revision ID: x3a0b5c94n26
Revises: w2z9a4b83m15
"""
import sqlalchemy as sa
from alembic import op

revision = "x3a0b5c94n26"
down_revision = "w2z9a4b83m15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fiscal_regimes", sa.Column("turnover_vat_pct", sa.Numeric(5, 2), server_default="0", nullable=False))
    # the starting value (then managed by SUPER_ADMIN): Simplificado 7 % of the turnover
    op.execute("UPDATE fiscal_regimes SET turnover_vat_pct = 7 WHERE name ILIKE '%simplific%'")


def downgrade() -> None:
    op.drop_column("fiscal_regimes", "turnover_vat_pct")
