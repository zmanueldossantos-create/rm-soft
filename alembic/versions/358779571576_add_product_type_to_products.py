"""Add product_type to products

Revision ID: 358779571576
Revises: 93e1f2d75f95
Create Date: 2026-08-24 14:47:17.453405

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '358779571576'
down_revision: Union[str, None] = '93e1f2d75f95'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    product_type_enum = sa.Enum('BEM', 'SERVICO', name='producttype')
    product_type_enum.create(op.get_bind())
    op.add_column(
        'products',
        sa.Column('product_type', product_type_enum, nullable=False, server_default='BEM')
    )
    # Drop the server default after backfilling existing rows - new rows
    # should always specify it explicitly via the application, not rely on DB default.
    op.alter_column('products', 'product_type', server_default=None)


def downgrade() -> None:
    op.drop_column('products', 'product_type')
    sa.Enum(name='producttype').drop(op.get_bind())
