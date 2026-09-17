"""Add allows_int and allows_out to fiscal_regimes

Revision ID: a02e6352b1ae
Revises: 1b703146ed84
Create Date: 2026-08-24 18:11:24.751015

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a02e6352b1ae'
down_revision: Union[str, None] = '1b703146ed84'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('fiscal_regimes', sa.Column('allows_int', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('fiscal_regimes', sa.Column('allows_out', sa.Boolean(), nullable=False, server_default='false'))
    op.alter_column('fiscal_regimes', 'allows_int', server_default=None)
    op.alter_column('fiscal_regimes', 'allows_out', server_default=None)


def downgrade() -> None:
    op.drop_column('fiscal_regimes', 'allows_out')
    op.drop_column('fiscal_regimes', 'allows_int')
