"""Contabilidade - «Fornecimentos e serviços de terceiros» in Contas por operação: the PGC account 75.2 suggested for
the companies whose chart is already started (the new operations are only suggested at the chart's start otherwise).

Revision ID: k4i8b1v59a81
Revises: j3h7a0u48z70
"""
from alembic import op

revision = "k4i8b1v59a81"
down_revision = "j3h7a0u48z70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO account_mappings (id, company_id, operation, account_id)
        SELECT gen_random_uuid(), a.company_id, 'PURCHASES_SERVICES', a.id
        FROM accounts a JOIN accounting_settings s ON s.company_id = a.company_id
        WHERE a.code = '75.2' AND a.is_active AND s.chart_source IS NOT NULL
          AND NOT EXISTS (SELECT 1 FROM accounts c WHERE c.parent_id = a.id)
          AND NOT EXISTS (SELECT 1 FROM account_mappings m WHERE m.company_id = a.company_id AND m.operation = 'PURCHASES_SERVICES')
    """)


def downgrade() -> None:
    op.execute("DELETE FROM account_mappings WHERE operation = 'PURCHASES_SERVICES'")
