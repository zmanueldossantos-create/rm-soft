"""Working documents never sent to the AGT (pro-forma, guias...) keep one series a year whatever the mode: the unused
ELETRONICA copies made beside a series already used (same company, type and year) are removed - they would repeat its
numbers.

Revision ID: m9k3d6715c37
Revises: l8j2c5604b26
"""
from alembic import op

revision = "m9k3d6715c37"
down_revision = "l8j2c5604b26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DELETE FROM document_series s
        USING document_types t
        WHERE s.document_type_id = t.id AND t.sent_to_agt = false AND s.issuance_mode = 'ELETRONICA'
          AND s.current_number = 0
          AND EXISTS (SELECT 1 FROM document_series o WHERE o.company_id = s.company_id
                      AND o.document_type_id = s.document_type_id AND o.year = s.year AND o.id <> s.id)
    """)


def downgrade() -> None:
    pass
