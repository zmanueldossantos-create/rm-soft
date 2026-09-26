"""add iec_amount and iselo_amount to invoice_lines - always 0 for now (not computed), prepares the A4 PDF/AGT layout columns for future implementation"""
from alembic import op
import sqlalchemy as sa

revision = 'r5t2u7v16g48'
down_revision = 'q4s1t6u05f37'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('invoice_lines', sa.Column('iec_amount', sa.Numeric(14, 2), nullable=False, server_default='0'))
    op.add_column('invoice_lines', sa.Column('iselo_amount', sa.Numeric(14, 2), nullable=False, server_default='0'))


def downgrade():
    op.drop_column('invoice_lines', 'iselo_amount')
    op.drop_column('invoice_lines', 'iec_amount')