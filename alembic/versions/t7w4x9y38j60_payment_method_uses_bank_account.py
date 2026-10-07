"""payment method uses_bank_account: which payment methods go through a bank account

Revision ID: t7w4x9y38j60
Revises: s6u3v8w27h59
"""
from alembic import op
import sqlalchemy as sa

revision = "t7w4x9y38j60"
down_revision = "s6u3v8w27h59"
branch_labels = None
depends_on = None

# The methods whose money lands on a bank account: transfer, Multicaixa references, credit / debit cards, cheque,
# electronic money. Cash, offsetting, barter, gift vouchers and "other" do not.
BANK_CODES = ("TB", "MB", "CC", "CD", "CH", "DE")


def upgrade() -> None:
    op.add_column("payment_method_catalog", sa.Column("uses_bank_account", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute(
        "UPDATE payment_method_catalog SET uses_bank_account = true WHERE code IN ("
        + ", ".join("'" + c + "'" for c in BANK_CODES) + ")"
    )


def downgrade() -> None:
    op.drop_column("payment_method_catalog", "uses_bank_account")
