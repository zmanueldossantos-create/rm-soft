"""payment method names with their accents - the AGT codes, the only thing the SAF-T declares, do not change

Revision ID: i8l5m0n49y71
Revises: h7k4l9m38x60
"""
from alembic import op
import sqlalchemy as sa

revision = "i8l5m0n49y71"
down_revision = "h7k4l9m38x60"
branch_labels = None
depends_on = None

# code -> (name with accents, previous name)
NAMES = {
    "CC": ("Cartão crédito", "Cartao credito"),
    "CD": ("Cartão débito", "Cartao debito"),
    "CH": ("Cheque bancário", "Cheque bancario"),
    "CI": ("Crédito documentário internacional", "Credito documentario internacional"),
    "CO": ("Cheque ou cartão oferta", "Cheque ou cartao oferta"),
    "CS": ("Compensação de saldos em conta corrente", "Compensacao de saldos em conta corrente"),
    "DE": ("Dinheiro electrónico", "Dinheiro electronico"),
    "MB": ("Referências de pagamento Multicaixa", "Referencias de pagamento Multicaixa"),
    "NU": ("Numerário", "Numerario"),
    "TB": ("Transferência bancária", "Transferencia bancaria"),
}


def _rename(index: int) -> None:
    for code, names in NAMES.items():
        op.execute(sa.text("UPDATE payment_method_catalog SET name = :name WHERE code = :code")
                   .bindparams(name=names[index], code=code))


def upgrade() -> None:
    _rename(0)


def downgrade() -> None:
    _rename(1)
