"""drop warehouses.gerido_por_familia_tipo: never had any effect nor a defined rule

Revision ID: x1a8b3c72n04
Revises: w0z7a2b61m93
"""
from alembic import op
import sqlalchemy as sa

revision = "x1a8b3c72n04"
down_revision = "w0z7a2b61m93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("warehouses", "gerido_por_familia_tipo")


def downgrade() -> None:
    op.add_column("warehouses", sa.Column("gerido_por_familia_tipo", sa.Boolean(), nullable=False, server_default=sa.false()))
