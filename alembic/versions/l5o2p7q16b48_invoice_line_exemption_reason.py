"""invoice lines: exemption_reason_snapshot - the official reason of the motive, copied with its code when issued
(issued lines filled from the catalog); M94 deactivated - absent from the AGT exemption table (M00-M93)

Revision ID: l5o2p7q16b48
Revises: k4n1o6p05a37
"""
from alembic import op
import sqlalchemy as sa

revision = "l5o2p7q16b48"
down_revision = "k4n1o6p05a37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoice_lines", sa.Column("exemption_reason_snapshot", sa.String(255), nullable=True))
    op.execute(
        "UPDATE invoice_lines l SET exemption_reason_snapshot = v.name FROM vat_codes v "
        "WHERE l.exemption_code IS NOT NULL AND v.code = l.exemption_code"
    )
    op.execute("UPDATE vat_codes SET is_active = false WHERE code = 'M94'")


def downgrade() -> None:
    op.drop_column("invoice_lines", "exemption_reason_snapshot")
