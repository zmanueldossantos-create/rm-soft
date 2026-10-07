"""Add PERDA movement type and loss_category

Revision ID: 656364042b58
Revises: c4cd41d24cea
Create Date: 2026-08-25 13:05:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '656364042b58'
down_revision: Union[str, None] = 'c4cd41d24cea'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add the new PERDA value to the existing movementtype enum.
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PERDA'")

    # Create the new losscategory enum type, then add the column.
    loss_category_enum = sa.Enum('EXPIRACAO', 'QUEBRA', 'ROUBO', 'OUTRO', name='losscategory')
    loss_category_enum.create(op.get_bind())
    op.add_column('stock_movements', sa.Column('loss_category', loss_category_enum, nullable=True))


def downgrade() -> None:
    op.drop_column('stock_movements', 'loss_category')
    sa.Enum(name='losscategory').drop(op.get_bind())
    # Note: Postgres does not support removing a value from an enum type
    # directly - a downgrade cannot cleanly remove 'PERDA' from movementtype.
