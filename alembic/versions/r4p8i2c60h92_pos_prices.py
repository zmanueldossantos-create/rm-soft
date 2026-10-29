"""Preço 2 / 3 and the free price, allowed per till (caixa) by the gestor like the billetage - no longer a permission
of the profiles (invoices:price_levels removed, with its grants). A line sold at a free price keeps the catalogue price
it replaced (invoice_lines.catalog_unit_price; price_level 0 = «Preço livre»).

Revision ID: r4p8i2c60h92
Revises: q3o7h1b59g81
"""
import sqlalchemy as sa
from alembic import op

revision = "r4p8i2c60h92"
down_revision = "q3o7h1b59g81"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("points_of_sale", sa.Column("allow_price_levels", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("points_of_sale", sa.Column("allow_free_price", sa.Boolean(), server_default="false", nullable=False))
    op.add_column("invoice_lines", sa.Column("catalog_unit_price", sa.Numeric(12, 2), nullable=True))
    # the tills where the cashier had been given «Preço 2 / 3» through the profiles keep it
    op.execute("""
        UPDATE points_of_sale SET allow_price_levels = true
        WHERE company_id IN (SELECT rp.company_id FROM role_permissions rp JOIN permissions p ON p.id = rp.permission_id
                             WHERE p.code = 'invoices:price_levels')
    """)
    for table in ("role_permissions", "company_permission_seeds"):
        op.execute(f"DELETE FROM {table} WHERE permission_id IN (SELECT id FROM permissions WHERE code = 'invoices:price_levels')")
    op.execute("DELETE FROM permissions WHERE code = 'invoices:price_levels'")


def downgrade() -> None:
    op.drop_column("invoice_lines", "catalog_unit_price")
    op.drop_column("points_of_sale", "allow_free_price")
    op.drop_column("points_of_sale", "allow_price_levels")
