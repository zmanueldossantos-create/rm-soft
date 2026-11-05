"""Caixas - a point of sale is one cash drawer, of kind CAIXA (sells) or COFRE (the safe: never sells). Every existing
point of sale is a CAIXA.

Revision ID: e8c1v5p93u25
Revises: d7b0u4o82t14
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e8c1v5p93u25"
down_revision = "d7b0u4o82t14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    kind = postgresql.ENUM("CAIXA", "COFRE", name="poskind")
    kind.create(op.get_bind(), checkfirst=True)
    op.add_column("points_of_sale", sa.Column(
        "kind", postgresql.ENUM("CAIXA", "COFRE", name="poskind", create_type=False), nullable=False, server_default="CAIXA",
    ))


def downgrade() -> None:
    op.drop_column("points_of_sale", "kind")
    postgresql.ENUM(name="poskind").drop(op.get_bind(), checkfirst=True)
