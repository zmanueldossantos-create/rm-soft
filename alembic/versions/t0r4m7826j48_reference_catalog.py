"""reference catalog: the platform's products by sector, with their sale units

Revision ID: t0r4m7826j48
Revises: s9q3l6715i37
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "t0r4m7826j48"
down_revision = "s9q3l6715i37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "reference_products",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("barcode", sa.String(50), nullable=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("category", sa.String(150), nullable=True),
        sa.Column("unit_of_measure_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("unit_of_measure_catalog.id"), nullable=False),
        sa.Column("tax_category", sa.String(3), nullable=False),
        sa.Column("exemption_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vat_codes.id"), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.Column("sectors", postgresql.ARRAY(sa.String(20)), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_reference_products_barcode", "reference_products", ["barcode"], unique=True,
                    postgresql_where=sa.text("barcode IS NOT NULL"))
    op.create_index("uq_reference_products_name_no_barcode", "reference_products", [sa.text("lower(name)")], unique=True,
                    postgresql_where=sa.text("barcode IS NULL"))
    op.create_table(
        "reference_product_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("reference_product_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("reference_products.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unit_of_measure_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("unit_of_measure_catalog.id"), nullable=False),
        sa.Column("factor", sa.Numeric(14, 4), nullable=False),
        sa.Column("barcode", sa.String(50), nullable=True),
        sa.Column("price", sa.Numeric(12, 2), nullable=True),
        sa.UniqueConstraint("reference_product_id", "unit_of_measure_id", name="uq_reference_product_unit"),
    )
    op.create_index("ix_reference_product_units_reference_product_id", "reference_product_units", ["reference_product_id"])


def downgrade() -> None:
    op.drop_table("reference_product_units")
    op.drop_table("reference_products")
