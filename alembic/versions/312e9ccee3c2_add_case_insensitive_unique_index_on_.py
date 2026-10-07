"""Add case-insensitive unique index on companies.name

Revision ID: 312e9ccee3c2
Revises: ef64a2ad8c64
Create Date: 2026-08-25 14:50:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = '312e9ccee3c2'
down_revision: Union[str, None] = 'ef64a2ad8c64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Guards against near-duplicate company names differing only by case
    # (e.g. "RM SOFT" vs "rm soft"), on top of the existing case-sensitive
    # unique constraint on companies.name.
    op.execute("CREATE UNIQUE INDEX uq_companies_name_lower ON companies (lower(name))")


def downgrade() -> None:
    op.execute("DROP INDEX uq_companies_name_lower")
