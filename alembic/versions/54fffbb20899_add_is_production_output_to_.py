"""Add is_production_output to StockMovement

Revision ID: 54fffbb20899
Revises: 3fa18dec9408
Create Date: 2026-08-26 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '54fffbb20899'
down_revision: Union[str, None] = '3fa18dec9408'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('stock_movements', sa.Column('is_production_output', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('stock_movements', 'is_production_output')
