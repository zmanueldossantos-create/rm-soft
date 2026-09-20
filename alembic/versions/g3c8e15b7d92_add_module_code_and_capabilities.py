"""add modules.code and module_capabilities (sector catalog, capabilities per module)

Nullable / additive only: existing modules and grants are untouched. The upgrade checks the
schema first, so running it on a database that already has these objects is harmless. Sector
modules and their default capabilities are created by the startup seed
(sector_service.seed_sector_catalog), not here.

Revision ID: g3c8e15b7d92
Revises: f2b9d6a0c413
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'g3c8e15b7d92'
down_revision: Union[str, None] = 'f2b9d6a0c413'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if 'code' not in {c['name'] for c in inspector.get_columns('modules')}:
        op.add_column('modules', sa.Column('code', sa.String(length=30), nullable=True))
        op.create_unique_constraint('uq_modules_code', 'modules', ['code'])
    if 'module_capabilities' not in inspector.get_table_names():
        op.create_table(
            'module_capabilities',
            sa.Column('module_id', sa.UUID(), nullable=False),
            sa.Column('capability', sa.String(length=30), nullable=False),
            sa.Column('is_enabled', sa.Boolean(), nullable=False, server_default=sa.text('true')),
            sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
            sa.ForeignKeyConstraint(['module_id'], ['modules.id']),
            sa.PrimaryKeyConstraint('module_id', 'capability'),
        )


def downgrade() -> None:
    # Configuration data is never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("module capabilities and sector codes are never dropped by a downgrade")