"""Tesouraria - the till names DE «Multicaixa Express» (the code of an Express payment, AGT: dinheiro electrónico),
and a supplier keeps the IBAN its transfers are paid to.

Revision ID: b5z8s2m60r92
Revises: a4y7r1l59q81
"""
import sqlalchemy as sa
from alembic import op

revision = "b5z8s2m60r92"
down_revision = "a4y7r1l59q81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # only when no label was chosen yet (the platform may have its own)
    op.execute("UPDATE payment_method_catalog SET short_label = 'Multicaixa Express' WHERE code = 'DE' AND short_label IS NULL")
    op.add_column("suppliers", sa.Column("iban", sa.String(50), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "iban")
    op.execute("UPDATE payment_method_catalog SET short_label = NULL WHERE code = 'DE' AND short_label = 'Multicaixa Express'")
