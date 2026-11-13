"""Fornecedores - every company gets its «Fornecedor diverso» (NIF 999999999, the anonymous NIF of the AGT): the
supplier of the purchases from someone without a NIF (a market seller), as the Consumidor final of the sales. New
companies get it at their creation (company_service); this gives it to the existing ones.

Revision ID: r2p5i8c26h58
Revises: q1o4h7b15g47
"""
from alembic import op

revision = "r2p5i8c26h58"
down_revision = "q1o4h7b15g47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        INSERT INTO suppliers (id, company_id, name, nif, notes, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), c.id, 'Fornecedor diverso', '999999999',
               'Compras a quem não tem NIF (mercado, pequeno comércio) - NIF anónimo da AGT', true, now(), now()
        FROM companies c
        WHERE NOT EXISTS (SELECT 1 FROM suppliers s WHERE s.company_id = c.id
                          AND (s.nif = '999999999' OR s.name = 'Fornecedor diverso'))
    """)


def downgrade() -> None:
    # only the untouched ones: a «Fornecedor diverso» already used by a document stays
    op.execute("""
        DELETE FROM suppliers s WHERE s.name = 'Fornecedor diverso' AND s.nif = '999999999'
        AND NOT EXISTS (SELECT 1 FROM purchase_invoices x WHERE x.supplier_id = s.id)
        AND NOT EXISTS (SELECT 1 FROM supplier_payments x WHERE x.supplier_id = s.id)
        AND NOT EXISTS (SELECT 1 FROM goods_movements x WHERE x.supplier_id = s.id)
        AND NOT EXISTS (SELECT 1 FROM stock_movement_documents x WHERE x.supplier_id = s.id)
        AND NOT EXISTS (SELECT 1 FROM account_links x WHERE x.entity_id = s.id)
    """)
