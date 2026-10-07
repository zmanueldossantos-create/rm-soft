"""Add unit_of_measure and batch_yield to Product; rename RecipeIngredient.quantity_per_unit to quantity_per_batch

Revision ID: edd97ab5e3cd
Revises: 62d8950dbdf6
Create Date: 2026-08-25 20:28:40.195135

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'edd97ab5e3cd'
down_revision: Union[str, None] = '62d8950dbdf6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('products', sa.Column('unit_of_measure', sa.String(length=30), nullable=True))
    op.add_column('products', sa.Column('batch_yield', sa.Numeric(precision=12, scale=3), nullable=False, server_default='1'))
    op.alter_column('products', 'batch_yield', server_default=None)

    # True rename - preserves existing recipe data, unlike drop+add.
    op.alter_column('recipe_ingredients', 'quantity_per_unit', new_column_name='quantity_per_batch')


def downgrade() -> None:
    op.alter_column('recipe_ingredients', 'quantity_per_batch', new_column_name='quantity_per_unit')
    op.drop_column('products', 'batch_yield')
    op.drop_column('products', 'unit_of_measure')
