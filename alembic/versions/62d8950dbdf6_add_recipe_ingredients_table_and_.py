"""Add recipe_ingredients table and PRODUCAO movement type

Revision ID: 62d8950dbdf6
Revises: 312e9ccee3c2
Create Date: 2026-08-25 15:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = '62d8950dbdf6'
down_revision: Union[str, None] = '312e9ccee3c2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE movementtype ADD VALUE IF NOT EXISTS 'PRODUCAO'")

    op.create_table(
        'recipe_ingredients',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False),
        sa.Column('finished_product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('ingredient_product_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('products.id'), nullable=False),
        sa.Column('quantity_per_unit', sa.Numeric(14, 4), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('finished_product_id', 'ingredient_product_id', name='uq_recipe_ingredient'),
    )
    op.create_index('ix_recipe_ingredients_company_id', 'recipe_ingredients', ['company_id'])
    op.create_index('ix_recipe_ingredients_finished_product_id', 'recipe_ingredients', ['finished_product_id'])
    op.create_index('ix_recipe_ingredients_ingredient_product_id', 'recipe_ingredients', ['ingredient_product_id'])


def downgrade() -> None:
    op.drop_table('recipe_ingredients')
    # Note: Postgres does not support removing a value from an enum type -
    # a downgrade cannot cleanly remove 'PRODUCAO' from movementtype.
