"""add open_account_transfers (insert-only audit of line moves between open accounts)

Revision ID: c91e5d7a2b36
Revises: a7c2d91e4b58
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'c91e5d7a2b36'
down_revision: Union[str, None] = 'a7c2d91e4b58'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'open_account_transfers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('source_account_id', sa.UUID(), nullable=False),
        sa.Column('target_account_id', sa.UUID(), nullable=False),
        sa.Column('source_line_id', sa.UUID(), nullable=False),
        sa.Column('target_line_id', sa.UUID(), nullable=False),
        sa.Column('name_snapshot', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Numeric(12, 3), nullable=False),
        sa.Column('unit_price', sa.Numeric(12, 2), nullable=False),
        sa.Column('moved_by_user_id', sa.UUID(), nullable=False),
        sa.Column('moved_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['source_account_id'], ['open_accounts.id']),
        sa.ForeignKeyConstraint(['target_account_id'], ['open_accounts.id']),
        sa.ForeignKeyConstraint(['source_line_id'], ['open_account_lines.id']),
        sa.ForeignKeyConstraint(['target_line_id'], ['open_account_lines.id']),
        sa.ForeignKeyConstraint(['moved_by_user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_open_account_transfers_company_id'), 'open_account_transfers', ['company_id'], unique=False)
    op.create_index(op.f('ix_open_account_transfers_source_account_id'), 'open_account_transfers', ['source_account_id'], unique=False)
    op.create_index(op.f('ix_open_account_transfers_target_account_id'), 'open_account_transfers', ['target_account_id'], unique=False)


def downgrade() -> None:
    # Audit trail: never dropped automatically (the app never deletes data).
    raise RuntimeError("open_account_transfers is an audit table and is never dropped by a downgrade")
