"""payment method short label - the name a cashier understands, shown on the till screens only; documents, reports
and the SAF-T keep the official AGT name and code

Revision ID: j9m6n1o50z82
Revises: i8l5m0n49y71
"""
from alembic import op
import sqlalchemy as sa

revision = "j9m6n1o50z82"
down_revision = "i8l5m0n49y71"
branch_labels = None
depends_on = None

LABELS = {"CD": "Multicaixa (cartão)", "MB": "Multicaixa (referência)"}


def upgrade() -> None:
    op.add_column("payment_method_catalog", sa.Column("short_label", sa.String(60), nullable=True))
    for code, label in LABELS.items():
        op.execute(sa.text("UPDATE payment_method_catalog SET short_label = :label WHERE code = :code")
                   .bindparams(label=label, code=code))


def downgrade() -> None:
    op.drop_column("payment_method_catalog", "short_label")
