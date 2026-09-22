"""add requires_payment_term to document_types (payment condition mandatory - e.g. Fatura)"""
from alembic import op
import sqlalchemy as sa

revision = 'n1p8q3r72c04'
down_revision = 'm9c6d2f57a41'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('document_types', sa.Column('requires_payment_term', sa.Boolean(), server_default='false', nullable=False))
    op.execute("UPDATE document_types SET requires_payment_term = true WHERE code = 'FT'")


def downgrade():
    op.drop_column('document_types', 'requires_payment_term')