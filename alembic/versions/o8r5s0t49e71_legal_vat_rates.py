"""legal_vat_rates: the legal VAT rate of each SAF-T category (ISE 0 %, RED 5 %, NOR 14 %), SUPER_ADMIN managed - the rates a
company receives for what its regime allows, instead of a list written in the code (INT and OUT added once confirmed)

Revision ID: o8r5s0t49e71
Revises: n7q4r9s38d60
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "o8r5s0t49e71"
down_revision = "n7q4r9s38d60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "legal_vat_rates",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("tax_category", sa.String(3), nullable=False, unique=True),
        sa.Column("name", sa.String(50), nullable=False),
        sa.Column("rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO legal_vat_rates (id, tax_category, name, rate) VALUES "
        "(gen_random_uuid(), 'ISE', 'Isento', 0), (gen_random_uuid(), 'RED', 'Taxa reduzida', 5), "
        "(gen_random_uuid(), 'NOR', 'Taxa normal', 14)"
    )


def downgrade() -> None:
    op.drop_table("legal_vat_rates")
