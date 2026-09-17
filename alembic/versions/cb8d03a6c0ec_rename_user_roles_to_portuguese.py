"""Rename user roles to Portuguese

Revision ID: cb8d03a6c0ec
Revises: f8f53b52fd1e
Create Date: 2026-08-20 17:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'cb8d03a6c0ec'
down_revision: Union[str, None] = 'f8f53b52fd1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE userrole RENAME VALUE 'GESTIONNAIRE' TO 'GESTOR'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'CAISSIER' TO 'CAIXA'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'MAGASINIER' TO 'ARMAZENISTA'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'COMPTABLE' TO 'CONTABILISTA'")


def downgrade() -> None:
    op.execute("ALTER TYPE userrole RENAME VALUE 'GESTOR' TO 'GESTIONNAIRE'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'CAIXA' TO 'CAISSIER'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'ARMAZENISTA' TO 'MAGASINIER'")
    op.execute("ALTER TYPE userrole RENAME VALUE 'CONTABILISTA' TO 'COMPTABLE'")
