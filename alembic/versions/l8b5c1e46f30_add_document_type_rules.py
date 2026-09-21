"""document_types: behaviour columns (rules) read by the code instead of comparing document types by name

Additive only: 14 columns with defaults, then filled in for the types whose rules are defined (FT, FR, NC, ND, RC, FP -
fiscal rules locked). The other types keep the defaults (everything off, lines allowed). Nothing is deleted.

Revision ID: l8b5c1e46f30
Revises: k7a4b0d35e29
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'l8b5c1e46f30'
down_revision: Union[str, None] = 'k7a4b0d35e29'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BOOLEANS_OFF = [
    'rules_locked', 'requires_origin', 'paid_on_issue', 'sent_to_agt', 'deducts_stock', 'accepts_credit_note',
    'accepts_debit_note', 'accepts_receipt', 'convertible', 'issuable_in_invoices', 'issuable_at_pos',
]


def _rule(section, sign, origin, lines, paid, agt, stock, nc, nd, rc, conv, invoices, pos):
    return dict(
        rules_locked=True, saft_section=section, revenue_sign=sign, requires_origin=origin, has_lines=lines,
        paid_on_issue=paid, sent_to_agt=agt, deducts_stock=stock, accepts_credit_note=nc, accepts_debit_note=nd,
        accepts_receipt=rc, convertible=conv, issuable_in_invoices=invoices, issuable_at_pos=pos,
    )


RULES = {
    #        section     sign origin lines  paid   agt    stock  nc     nd     rc     conv   invoices pos
    'FT': _rule('INVOICES', 1, False, True, False, True, True, True, True, True, False, True, True),
    'FR': _rule('INVOICES', 1, False, True, True, True, True, True, True, False, False, True, True),
    'NC': _rule('INVOICES', -1, True, True, False, True, False, False, False, False, False, False, False),
    'ND': _rule('INVOICES', 1, True, True, False, True, False, False, False, False, False, False, False),
    'RC': _rule('PAYMENTS', 0, True, False, False, True, False, False, False, False, False, False, False),
    'FP': _rule('WORKING', 0, False, True, False, False, False, False, False, False, True, True, True),
}


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('document_types')}
    for name in BOOLEANS_OFF:
        if name not in existing:
            op.add_column('document_types', sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))
    if 'has_lines' not in existing:
        op.add_column('document_types', sa.Column('has_lines', sa.Boolean(), nullable=False, server_default=sa.true()))
    if 'saft_section' not in existing:
        op.add_column('document_types', sa.Column('saft_section', sa.String(length=10), nullable=False, server_default='NONE'))
    if 'revenue_sign' not in existing:
        op.add_column('document_types', sa.Column('revenue_sign', sa.SmallInteger(), nullable=False, server_default='0'))

    for code, values in RULES.items():
        assignments = ', '.join(f'{key} = :{key}' for key in values)  # keys are the constants above
        bind.execute(sa.text(f'UPDATE document_types SET {assignments} WHERE code = :code'), {**values, 'code': code})


def downgrade() -> None:
    # Rules data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError('document type rules are never dropped by a downgrade')