"""add description to document_types - short blurb shown on the type-selection cards in the future stepped invoice wizard"""
from alembic import op
import sqlalchemy as sa

revision = 's6u3v8w27h59'
down_revision = 'r5t2u7v16g48'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_types', sa.Column('description', sa.String(200), nullable=True))


def downgrade():
    op.drop_column('document_types', 'description')