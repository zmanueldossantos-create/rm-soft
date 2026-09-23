"""drop subject_to_return from products and services - never read anywhere in the codebase (dead field)"""
from alembic import op
import sqlalchemy as sa

revision = 'q4s1t6u05f37'
down_revision = 'p3r0s5t94e26'
branch_labels = None
depends_on = None


def upgrade():
    op.drop_column('products', 'subject_to_return')
    op.drop_column('services', 'subject_to_return')


def downgrade():
    op.add_column('products', sa.Column('subject_to_return', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('services', sa.Column('subject_to_return', sa.Boolean(), nullable=False, server_default='false'))