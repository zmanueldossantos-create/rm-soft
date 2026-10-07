"""Remove ADMIN role

Revision ID: f558ce18dee5
Revises: 2ca52b339d01
Create Date: 2026-08-21 22:13:00.000000

"""
from typing import Sequence, Union

from alembic import op

revision: str = 'f558ce18dee5'
down_revision: Union[str, None] = '2ca52b339d01'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Postgres cannot remove a value from an enum type directly - recreate
    # the type without ADMIN, remapping the users.role column through it.
    # Safe here because no user with role=ADMIN exists (verified beforehand).
    op.execute("ALTER TYPE userrole RENAME TO userrole_old")
    op.execute("CREATE TYPE userrole AS ENUM ('SUPER_ADMIN', 'GESTOR', 'CAIXA', 'ARMAZENISTA', 'CONTABILISTA')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::text::userrole")
    op.execute("DROP TYPE userrole_old")


def downgrade() -> None:
    op.execute("ALTER TYPE userrole RENAME TO userrole_new")
    op.execute("CREATE TYPE userrole AS ENUM ('SUPER_ADMIN', 'GESTOR', 'ADMIN', 'CAIXA', 'ARMAZENISTA', 'CONTABILISTA')")
    op.execute("ALTER TABLE users ALTER COLUMN role TYPE userrole USING role::text::userrole")
    op.execute("DROP TYPE userrole_new")
