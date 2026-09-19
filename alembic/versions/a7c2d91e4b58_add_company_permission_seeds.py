"""add company_permission_seeds (seed defaults once per company/permission)

Revision ID: a7c2d91e4b58
Revises: f3fe86a6c959
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a7c2d91e4b58'
down_revision: Union[str, None] = 'f3fe86a6c959'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'company_permission_seeds',
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('permission_id', sa.UUID(), nullable=False),
        sa.Column('seeded_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id']),
        sa.ForeignKeyConstraint(['permission_id'], ['permissions.id']),
        sa.PrimaryKeyConstraint('company_id', 'permission_id'),
    )

    # Backfill: every company that already went through the boot-time seed
    # (= has at least one role_permissions row) is marked as seeded for every
    # existing permission, so grants a GESTOR removed stay removed. Companies
    # with no rows at all stay unseeded and receive their defaults at the next seed.
    op.execute("""
        INSERT INTO company_permission_seeds (company_id, permission_id)
        SELECT c.id, p.id
        FROM companies c CROSS JOIN permissions p
        WHERE c.id IN (SELECT DISTINCT company_id FROM role_permissions)
    """)

    # GESTOR now always has every permission (checked in code, never stored):
    # its rows are redundant and would mislead the matrix.
    op.execute("DELETE FROM role_permissions WHERE role = 'GESTOR'")


def downgrade() -> None:
    op.drop_table('company_permission_seeds')