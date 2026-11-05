"""Tesouraria - a till's cash deposited on a bank account, and cash withdrawn from it into a till or the cofre: a cash
movement (saída / entrada externa) with the bank account of the company.

Revision ID: f9d2w6q04v36
Revises: e8c1v5p93u25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f9d2w6q04v36"
down_revision = "e8c1v5p93u25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cash_movements", sa.Column("bank_account_id", postgresql.UUID(as_uuid=True),
                                              sa.ForeignKey("company_bank_accounts.id"), nullable=True))
    op.create_index("ix_cash_movements_bank_account_id", "cash_movements", ["bank_account_id"])


def downgrade() -> None:
    op.drop_index("ix_cash_movements_bank_account_id", table_name="cash_movements")
    op.drop_column("cash_movements", "bank_account_id")
