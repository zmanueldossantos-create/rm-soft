"""products.vat_id becomes nullable (a raw material carries no VAT rate)

A raw material is never sold: invoicing, the POS and open accounts refuse it (see
invoice_service / open_account_service). product_service still requires a VAT rate for every
other product. Only the NOT NULL constraint is dropped - no row is touched. The upgrade checks the
column first, so running it on a database that is already nullable is harmless.

Revision ID: h4d1c7a90e3b6
Revises: g3c8e15b7d92
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'h4d1c7a90e3b6'
down_revision: Union[str, None] = 'g3c8e15b7d92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    column = next(c for c in inspector.get_columns('products') if c['name'] == 'vat_id')
    if not column['nullable']:
        op.alter_column('products', 'vat_id', existing_type=sa.UUID(), nullable=True)


def downgrade() -> None:
    # Restoring NOT NULL would fail (or force a fake rate) once raw materials without VAT exist.
    raise RuntimeError("products.vat_id stays nullable: raw materials carry no VAT rate")