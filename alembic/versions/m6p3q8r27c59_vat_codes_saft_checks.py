"""vat_codes: the SAF-T rule of an exemption motive in the database - code M + 2 digits, reason of 6 to 60 characters
(the catalog is now the only source of the reasons copied on exempt lines)

Revision ID: m6p3q8r27c59
Revises: l5o2p7q16b48
"""
from alembic import op

revision = "m6p3q8r27c59"
down_revision = "l5o2p7q16b48"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_check_constraint("ck_vat_codes_code_format", "vat_codes", "code ~ '^M[0-9]{2}$'")
    op.create_check_constraint("ck_vat_codes_name_length", "vat_codes", "char_length(name) BETWEEN 6 AND 60")


def downgrade() -> None:
    op.drop_constraint("ck_vat_codes_name_length", "vat_codes", type_="check")
    op.drop_constraint("ck_vat_codes_code_format", "vat_codes", type_="check")
