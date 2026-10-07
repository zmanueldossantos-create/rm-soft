"""sale unit controls: fixed factor on universal units (a dozen is always 12), per-company price / factor checks

Revision ID: v9y6z1a50l82
Revises: u8x5y0z49k71
"""
from alembic import op
import sqlalchemy as sa

revision = "v9y6z1a50l82"
down_revision = "u8x5y0z49k71"
branch_labels = None
depends_on = None

CHECKS = ("sale_unit_check_above_base", "sale_unit_check_below_cost", "sale_unit_check_same_factor")


def upgrade() -> None:
    op.add_column("unit_of_measure_catalog", sa.Column("fixed_factor", sa.Numeric(14, 4), nullable=True))
    op.execute("UPDATE unit_of_measure_catalog SET fixed_factor = 12 WHERE code = 'DZ'")
    for column in CHECKS:
        op.add_column("companies", sa.Column(column, sa.String(5), nullable=False, server_default="warn"))


def downgrade() -> None:
    for column in CHECKS:
        op.drop_column("companies", column)
    op.drop_column("unit_of_measure_catalog", "fixed_factor")
