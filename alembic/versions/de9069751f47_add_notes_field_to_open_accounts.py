"""add notes field to open_accounts

Revision ID: de9069751f47
Revises: 0a0aebfd4dd0
Create Date: 2026-09-13 21:28:40.576287

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'de9069751f47'
down_revision: Union[str, None] = '0a0aebfd4dd0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.
    op.add_column('open_accounts', sa.Column('notes', sa.String(length=500), nullable=True))
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_column('open_accounts', 'notes')
    # ### end Alembic commands ###
