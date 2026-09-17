"""Add RECIBO value to InvoiceType enum

Revision ID: 9a7e6af996ee
Revises: a57567888fac
Create Date: 2026-09-02 15:39:01.229573

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9a7e6af996ee'
down_revision: Union[str, None] = 'a57567888fac'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE invoicetype ADD VALUE IF NOT EXISTS 'RECIBO'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values directly - a downgrade
    # would require recreating the type, which is out of scope for this simple addition.
    pass
