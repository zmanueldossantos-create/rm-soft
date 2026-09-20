"""add services.duration_minutes (default length of a booking for this service)

Nullable and optional: existing services are untouched (no duration = no default length).
The upgrade checks the table first, so running it on a database that already has the
column is harmless.

Revision ID: f2b9d6a0c413
Revises: e5c37a1d9b48
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'f2b9d6a0c413'
down_revision: Union[str, None] = 'e5c37a1d9b48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    existing = {c['name'] for c in inspector.get_columns('services')}
    if 'duration_minutes' not in existing:
        op.add_column('services', sa.Column('duration_minutes', sa.Integer(), nullable=True))


def downgrade() -> None:
    # Configuration data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("services.duration_minutes is never dropped by a downgrade")
