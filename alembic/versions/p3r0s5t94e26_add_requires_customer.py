"""add requires_customer to document_types (a customer must be identified - e.g. Fatura)"""
from alembic import op
import sqlalchemy as sa

revision = 'p3r0s5t94e26'
down_revision = 'o2q9r4s83d15'
branch_labels = None
depends_on = None

# Read by tests/conftest.py to keep the test fixtures' document type rules in sync with this migration
# without duplicating the SQL UPDATE below - see _load_document_type_rules.
RULES_OVERRIDES = {"FT": {"requires_customer": True}}


def upgrade():
    op.add_column('document_types', sa.Column('requires_customer', sa.Boolean(), server_default='false', nullable=False))
    op.execute("UPDATE document_types SET requires_customer = true WHERE code = 'FT'")


def downgrade():
    op.drop_column('document_types', 'requires_customer')