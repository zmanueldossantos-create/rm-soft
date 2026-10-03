"""fiscal_regimes: required_exemption_id (the motive every exempt article carries under the regime) and the regimes
set as the AGT documents show them: Geral NOR/RED/ISE; Simplificado ISE with M00 (IVA - Regime Simplificado);
Exclusao ISE with M04 (IVA - Regime de Exclusao). INT and OUT stay off until an accountant confirms them.

Revision ID: n7q4r9s38d60
Revises: m6p3q8r27c59
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "n7q4r9s38d60"
down_revision = "m6p3q8r27c59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("fiscal_regimes", sa.Column("required_exemption_id", UUID(as_uuid=True), sa.ForeignKey("vat_codes.id"), nullable=True))
    op.execute("UPDATE fiscal_regimes SET allows_nor = true, allows_red = true, allows_ise = true, allows_int = false, "
               "allows_out = false, required_exemption_id = NULL WHERE name = 'Regime Geral'")
    op.execute("UPDATE fiscal_regimes SET allows_nor = false, allows_red = false, allows_ise = true, allows_int = false, "
               "allows_out = false, required_exemption_id = (SELECT id FROM vat_codes WHERE code = 'M00') WHERE name = 'Regime Simplificado'")
    op.execute("UPDATE fiscal_regimes SET allows_nor = false, allows_red = false, allows_ise = true, allows_int = false, "
               "allows_out = false, required_exemption_id = (SELECT id FROM vat_codes WHERE code = 'M04') WHERE name = 'Regime de Exclusao'")


def downgrade() -> None:
    op.drop_column("fiscal_regimes", "required_exemption_id")
