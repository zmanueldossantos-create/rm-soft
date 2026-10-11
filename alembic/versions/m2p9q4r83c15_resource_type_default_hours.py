"""resource types: usual entry and exit hours of a booking (a room: 14:00 -> 12:00 the next day)

Revision ID: m2p9q4r83c15
Revises: l1o8p3q72b04
"""
from alembic import op
import sqlalchemy as sa

revision = "m2p9q4r83c15"
down_revision = "l1o8p3q72b04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("resource_type_catalog", sa.Column("default_start_time", sa.Time(), nullable=True))
    op.add_column("resource_type_catalog", sa.Column("default_end_time", sa.Time(), nullable=True))
    # the types that already require a service are the rooms: the usual hotel hours
    op.execute(
        "UPDATE resource_type_catalog SET default_start_time = '14:00', default_end_time = '12:00' "
        "WHERE requires_service"
    )


def downgrade() -> None:
    op.drop_column("resource_type_catalog", "default_end_time")
    op.drop_column("resource_type_catalog", "default_start_time")
