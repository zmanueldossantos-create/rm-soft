"""add requires_service and service-to-resource-type link

Revision ID: 4cf1c781af9f
Revises: 8c5d0b572624
Create Date: 2026-09-14 15:57:10.884566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4cf1c781af9f'
down_revision: Union[str, None] = '8c5d0b572624'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.
    # server_default is required here - resource_type_catalog already has existing rows
    # (e.g. "CHAMBRE") that a plain NOT NULL add_column would reject outright.
    op.add_column('resource_type_catalog', sa.Column('requires_service', sa.Boolean(), nullable=False, server_default=sa.text('false')))
    op.add_column('services', sa.Column('resource_type_id', sa.UUID(), nullable=True))
    op.create_foreign_key(None, 'services', 'resource_type_catalog', ['resource_type_id'], ['id'])
    # ### end Alembic commands ###


def downgrade() -> None:
    op.drop_constraint(None, 'services', type_='foreignkey')
    op.drop_column('services', 'resource_type_id')
    op.drop_column('resource_type_catalog', 'requires_service')
    # ### end Alembic commands ###
