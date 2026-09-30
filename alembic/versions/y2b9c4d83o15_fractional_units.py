"""fractional units (KG, L take decimal quantities) replace products.is_sold_by_weight (unused: no product had it)

Revision ID: y2b9c4d83o15
Revises: x1a8b3c72n04
"""
from alembic import op
import sqlalchemy as sa

revision = "y2b9c4d83o15"
down_revision = "x1a8b3c72n04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("unit_of_measure_catalog", sa.Column("is_fractional", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.execute("UPDATE unit_of_measure_catalog SET is_fractional = true WHERE code IN ('KG', 'L')")
    op.drop_column("products", "is_sold_by_weight")


def downgrade() -> None:
    op.add_column("products", sa.Column("is_sold_by_weight", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.drop_column("unit_of_measure_catalog", "is_fractional")
