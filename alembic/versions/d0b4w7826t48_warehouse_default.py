"""warehouses.is_default (the gestor's «Armazém por defeito»: Stock opens with it, Compras proposes it)

Revision ID: d0b4w7826t48
Revises: c9a3v6715s37
"""
import sqlalchemy as sa
from alembic import op

revision = "d0b4w7826t48"
down_revision = "c9a3v6715s37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("warehouses", sa.Column("is_default", sa.Boolean(), nullable=False, server_default="false"))
    op.create_index("uq_warehouses_one_default", "warehouses", ["company_id"], unique=True,
                    postgresql_where=sa.text("is_default"))


def downgrade() -> None:
    op.drop_index("uq_warehouses_one_default", table_name="warehouses")
    op.drop_column("warehouses", "is_default")
