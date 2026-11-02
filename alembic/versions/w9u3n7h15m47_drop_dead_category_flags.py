"""product_categories / service_types: «Não disponível em compras» and «Não disponível no POS» removed - never read
by any screen or service (the till is set per article and by «Disponível nas caixas de»). «Não disponível em vendas»
stays: it keeps a category out of the public catalogue (the website), and the screen now says so.

Revision ID: w9u3n7h15m47
Revises: v8t2m6g04l36
"""
import sqlalchemy as sa
from alembic import op

revision = "w9u3n7h15m47"
down_revision = "v8t2m6g04l36"
branch_labels = None
depends_on = None

TABLES = ("product_categories", "service_types")


def upgrade() -> None:
    for table in TABLES:
        op.drop_column(table, "not_available_purchases")
        op.drop_column(table, "not_available_pos")


def downgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column("not_available_pos", sa.Boolean(), server_default="false", nullable=False))
        op.add_column(table, sa.Column("not_available_purchases", sa.Boolean(), server_default="false", nullable=False))
