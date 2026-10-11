"""customers: a final consumer (NIF 999999999) is a pessoa singular - never subject to a withholding

Revision ID: o4r1s6t05e37
Revises: n3q0r5s94d26
"""
from alembic import op

revision = "o4r1s6t05e37"
down_revision = "n3q0r5s94d26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE customers SET legal_person_type = 'FISICA', withholding_tax_id = NULL WHERE is_final_consumer")


def downgrade() -> None:
    pass  # the old type was a wrong default, not a choice: nothing to restore
