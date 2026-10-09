"""angolan banks catalog - the banks of the national financial system, added once for every installation; a bank
whose acronym already exists (whatever its case) is left as it is

Revision ID: k0n7o2p61a93
Revises: j9m6n1o50z82
"""
from alembic import op
import sqlalchemy as sa

revision = "k0n7o2p61a93"
down_revision = "j9m6n1o50z82"
branch_labels = None
depends_on = None

# (acronym, full name) - BAI is usually there already: it is skipped, never overwritten
BANKS = [
    ("BAI", "Banco Angolano de Investimentos"),
    ("BIC", "Banco BIC"),
    ("Yetu", "Banco Yetu"),
    ("Sol", "Banco Sol"),
    ("BNI", "Banco de Negócios Internacional"),
    ("BDA", "Banco de Desenvolvimento de Angola"),
    ("BCA", "Banco Comercial Angolano, S.A."),
    ("BCH", "Banco Comercial do Huambo"),
    ("BFA", "Banco de Fomento Angola"),
    ("BPC", "Banco de Poupança e Crédito"),
    ("BE", "Banco Económico"),
    ("BRK", "Banco Regional do Keve"),
    ("BIR", "Banco de Investimento Rural"),
    ("BMA", "Banco Millennium Atlântico"),
    ("BCS", "Banco de Crédito do Sul, S.A."),
    ("VTB África", "Banco VTB África S.A."),
    ("Finibanco", "Finibanco Angola, S.A."),
    ("SBA", "Standard Bank Angola"),
    ("BCG", "Banco Caixa Geral Angola"),
    ("BOC", "Banco da China Lda - Sucursal de Luanda"),
    ("Valor", "Banco Valor S.A."),
    ("Prestígio", "Banco Prestígio"),
    ("BAI Micro Finanças", "Banco BAI Micro Finanças S.A."),
    ("BCI", "Banco de Comércio e Indústria"),
]


def upgrade() -> None:
    for acronym, full_name in BANKS:
        op.execute(
            sa.text(
                "INSERT INTO banks (id, acronym, full_name, is_active) "
                "VALUES (gen_random_uuid(), :acronym, :full_name, true) "
                "ON CONFLICT (lower(acronym)) DO NOTHING"
            ).bindparams(acronym=acronym, full_name=full_name)
        )


def downgrade() -> None:
    # only the banks this migration added (BAI predates it) and that no company bank account uses
    for acronym, _ in BANKS[1:]:
        op.execute(
            sa.text(
                "DELETE FROM banks b WHERE lower(b.acronym) = lower(:acronym) "
                "AND NOT EXISTS (SELECT 1 FROM company_bank_accounts a WHERE a.bank_id = b.id)"
            ).bindparams(acronym=acronym)
        )
