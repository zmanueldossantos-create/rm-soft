"""add bookings.guest_name and bookings.party_size (free-text guest / number of guests)

Both columns are nullable and existing rows are untouched. The upgrade checks the table
first, so running it on a database that already has the columns is harmless.

Revision ID: e5c37a1d9b48
Revises: d4a83b91f0c7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'e5c37a1d9b48'
down_revision: Union[str, None] = 'd4a83b91f0c7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c['name'] for c in inspector.get_columns('bookings')}
    if 'guest_name' not in existing:
        op.add_column('bookings', sa.Column('guest_name', sa.String(length=150), nullable=True))
    if 'party_size' not in existing:
        op.add_column('bookings', sa.Column('party_size', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Guest data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("bookings.guest_name / party_size hold guest data and are never dropped by a downgrade")
