"""open_account_lines : unite de vente de la ligne (emballage, facteur, code), comme le panier de caisse

Revision ID: b1e8f3g72r04
Revises: a0d7e2f61q93
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "b1e8f3g72r04"
down_revision = "a0d7e2f61q93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("open_account_lines", sa.Column("sale_unit_id", UUID(as_uuid=True), nullable=True))
    op.add_column("open_account_lines", sa.Column("unit_factor", sa.Numeric(12, 4), nullable=False, server_default="1"))
    op.add_column("open_account_lines", sa.Column("unit_code_snapshot", sa.String(10), nullable=True))
    op.create_foreign_key(
        "fk_open_account_lines_sale_unit_id", "open_account_lines", "product_sale_units", ["sale_unit_id"], ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_open_account_lines_sale_unit_id", "open_account_lines", type_="foreignkey")
    op.drop_column("open_account_lines", "unit_code_snapshot")
    op.drop_column("open_account_lines", "unit_factor")
    op.drop_column("open_account_lines", "sale_unit_id")
