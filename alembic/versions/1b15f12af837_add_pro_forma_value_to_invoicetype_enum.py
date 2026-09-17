"""Add PRO_FORMA value to InvoiceType enum

Revision ID: 1b15f12af837
Revises: 9a7e6af996ee
Create Date: 2026-09-03 00:07:09.519656

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '1b15f12af837'
down_revision: Union[str, None] = '9a7e6af996ee'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE invoicetype ADD VALUE IF NOT EXISTS 'PRO_FORMA'")


def downgrade() -> None:
    pass  # cannot remove enum values in PostgreSQL
