"""vat_rates: every company receives the active legal rates its regime allows and it does not hold yet (by category) -
the companies created before the regimes were fixed only had NOR, so a general-regime company could sell neither exempt
nor 5 % goods. Nothing existing is changed.

Revision ID: p9s6t1u50f82
Revises: o8r5s0t49e71
"""
from alembic import op

revision = "p9s6t1u50f82"
down_revision = "o8r5s0t49e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Same rule as company_service._legal_rates_for: a legal rate is received when the regime's allows_<category> is set,
    # or always when the company has no regime.
    op.execute("""
        INSERT INTO vat_rates (id, company_id, name, rate, tax_category, is_active)
        SELECT gen_random_uuid(), c.id, l.name, l.rate, l.tax_category, true
        FROM companies c
        CROSS JOIN legal_vat_rates l
        LEFT JOIN fiscal_regimes r ON r.id = c.fiscal_regime_id
        WHERE l.is_active
          AND (r.id IS NULL
               OR (l.tax_category = 'NOR' AND r.allows_nor) OR (l.tax_category = 'RED' AND r.allows_red)
               OR (l.tax_category = 'ISE' AND r.allows_ise) OR (l.tax_category = 'INT' AND r.allows_int)
               OR (l.tax_category = 'OUT' AND r.allows_out))
          AND NOT EXISTS (SELECT 1 FROM vat_rates v WHERE v.company_id = c.id AND v.tax_category = l.tax_category)
    """)


def downgrade() -> None:
    pass
