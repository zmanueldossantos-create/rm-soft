"""product sale units: several ways to sell a product (pallet / egg, box / blister / tablet), stock in base units

Revision ID: u8x5y0z49k71
Revises: t7w4x9y38j60
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "u8x5y0z49k71"
down_revision = "t7w4x9y38j60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_sale_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("unit_of_measure_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("unit_of_measure_catalog.id"), nullable=False),
        sa.Column("factor", sa.Numeric(14, 4), nullable=False),
        sa.Column("price", sa.Numeric(12, 2), nullable=False),
        sa.Column("barcode", sa.String(50), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("product_id", "unit_of_measure_id", name="uq_product_sale_unit"),
    )
    op.create_index("ix_product_sale_units_company_id", "product_sale_units", ["company_id"])
    op.create_index("ix_product_sale_units_product_id", "product_sale_units", ["product_id"])
    op.create_index("ix_product_sale_units_barcode", "product_sale_units", ["barcode"])


def downgrade() -> None:
    op.drop_table("product_sale_units")
