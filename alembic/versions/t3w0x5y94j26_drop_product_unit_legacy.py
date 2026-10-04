"""products: unit_of_measure_legacy dropped - the old free-text unit, empty everywhere since the unit catalog

Revision ID: t3w0x5y94j26
Revises: s2v9w4x83i15
"""
from alembic import op
import sqlalchemy as sa

revision = "t3w0x5y94j26"
down_revision = "s2v9w4x83i15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("products", "unit_of_measure_legacy")


def downgrade() -> None:
    op.add_column("products", sa.Column("unit_of_measure_legacy", sa.String(30), nullable=True))
