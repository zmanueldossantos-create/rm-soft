"""vat_rates: one rate per tax code per company - rates come from the legal catalog through the regime only; the manual
per-company management is gone

Revision ID: z9c6d1e50p82
Revises: y8b5c0d49o71
"""
from alembic import op

revision = "z9c6d1e50p82"
down_revision = "y8b5c0d49o71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint("uq_vat_rates_company_category", "vat_rates", ["company_id", "tax_category"])


def downgrade() -> None:
    op.drop_constraint("uq_vat_rates_company_category", "vat_rates", type_="unique")
