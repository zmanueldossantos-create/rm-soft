"""warehouse locations (emplacements)

Where the goods are put away inside a warehouse (optional), and where each product is kept in each warehouse.

Revision ID: g6e1f4593w15
Revises: f5d9e3482v04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "g6e1f4593w15"
down_revision = "f5d9e3482v04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warehouse_locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False, index=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("warehouse_id", "code", name="uq_warehouse_location_code"),
    )
    op.create_table(
        "product_locations",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False, index=True),
        sa.Column("location_id", UUID(as_uuid=True), sa.ForeignKey("warehouse_locations.id"), nullable=False, index=True),
        sa.UniqueConstraint("product_id", "warehouse_id", name="uq_product_location_warehouse"),
    )


def downgrade() -> None:
    op.drop_table("product_locations")
    op.drop_table("warehouse_locations")
