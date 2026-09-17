"""add internal_use_only flag to products

Revision ID: 176db455cb38
Revises: c49f2476a4c3
Create Date: 2026-09-16 23:45:49.057287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '176db455cb38'
down_revision: Union[str, None] = 'c49f2476a4c3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.
    # server_default is required - products table already has existing rows.
    op.add_column('products', sa.Column('internal_use_only', sa.Boolean(), nullable=False, server_default=sa.text('false')))


def downgrade() -> None:
    op.drop_column('products', 'internal_use_only')
