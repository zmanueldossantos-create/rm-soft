"""Tesouraria - the bank accounts: their opening balance (the bank statement's balance on the day the company starts
following the account in RM Soft) and that day. The movements of each account (receipts and sales collected on it,
supplier payments made from it) are read from the documents; only this starting point is stored.

Revision ID: y2w5p9j37o69
Revises: x1v4o8i26n58
"""
import sqlalchemy as sa
from alembic import op

revision = "y2w5p9j37o69"
down_revision = "x1v4o8i26n58"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("company_bank_accounts", sa.Column("opening_balance", sa.Numeric(14, 2), nullable=False, server_default="0"))
    op.add_column("company_bank_accounts", sa.Column("opening_date", sa.Date(), nullable=True))


def downgrade() -> None:
    op.drop_column("company_bank_accounts", "opening_date")
    op.drop_column("company_bank_accounts", "opening_balance")
