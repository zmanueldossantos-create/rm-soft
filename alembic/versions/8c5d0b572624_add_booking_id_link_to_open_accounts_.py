"""add booking_id link to open_accounts for hotel check-in/check-out

Revision ID: 8c5d0b572624
Revises: d3fd5f06f398
Create Date: 2026-09-14 12:55:56.977850

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c5d0b572624'
down_revision: Union[str, None] = 'd3fd5f06f398'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.
    op.add_column('open_accounts', sa.Column('booking_id', sa.UUID(), nullable=True))
    op.create_index(op.f('ix_open_accounts_booking_id'), 'open_accounts', ['booking_id'], unique=False)
    op.create_foreign_key(None, 'open_accounts', 'bookings', ['booking_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_constraint(None, 'open_accounts', type_='foreignkey')
    op.drop_index(op.f('ix_open_accounts_booking_id'), table_name='open_accounts')
    op.drop_column('open_accounts', 'booking_id')
    # ### end Alembic commands ###
