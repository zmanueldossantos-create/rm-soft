"""products.prepared_in_kitchen : un article prepare en cuisine (un plat) - ce que la cuisine voit

Revision ID: c2f9g4h83s15
Revises: b1e8f3g72r04
"""
from alembic import op
import sqlalchemy as sa

revision = "c2f9g4h83s15"
down_revision = "b1e8f3g72r04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("prepared_in_kitchen", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("products", "prepared_in_kitchen")
