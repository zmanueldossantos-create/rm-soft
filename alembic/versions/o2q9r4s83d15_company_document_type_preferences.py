"""add company_document_type_preferences (per-company override of requires_payment_term)

Preserves current behaviour for existing companies: inserts a preference row with requires_payment_term=true
for every existing company, for the document types where the platform catalog already sets it (today: FT).
New companies get no row (follow the platform default), same split as available_at_pos.

Revision ID: o2q9r4s83d15
Revises: n1p8q3r72c04
"""
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'o2q9r4s83d15'
down_revision = 'n1p8q3r72c04'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'company_document_type_preferences',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('company_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('companies.id'), nullable=False, index=True),
        sa.Column('document_type_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('document_types.id'), nullable=False, index=True),
        sa.Column('requires_payment_term', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint('company_id', 'document_type_id', name='uq_company_document_type_pref'),
    )

    conn = op.get_bind()
    document_type_ids = [row[0] for row in conn.execute(
        sa.text("SELECT id FROM document_types WHERE is_active = true AND requires_payment_term = true")
    )]
    company_ids = [row[0] for row in conn.execute(sa.text("SELECT id FROM companies"))]
    if document_type_ids and company_ids:
        table = sa.table(
            'company_document_type_preferences',
            sa.column('id', postgresql.UUID(as_uuid=True)),
            sa.column('company_id', postgresql.UUID(as_uuid=True)),
            sa.column('document_type_id', postgresql.UUID(as_uuid=True)),
            sa.column('requires_payment_term', sa.Boolean()),
        )
        conn.execute(table.insert(), [
            {'id': uuid.uuid4(), 'company_id': cid, 'document_type_id': did, 'requires_payment_term': True}
            for cid in company_ids for did in document_type_ids
        ])


def downgrade():
    op.drop_table('company_document_type_preferences')