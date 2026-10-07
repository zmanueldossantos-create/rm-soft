"""Add is_raw_material to Product

Revision ID: 3fa18dec9408
Revises: edd97ab5e3cd
Create Date: 2026-08-26 10:12:46.595697

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '3fa18dec9408'
down_revision: Union[str, None] = 'edd97ab5e3cd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('is_raw_material', sa.Boolean(), nullable=False, server_default='false'))
    op.alter_column('products', 'is_raw_material', server_default=None)


def downgrade() -> None:
    op.drop_column('products', 'is_raw_material')
