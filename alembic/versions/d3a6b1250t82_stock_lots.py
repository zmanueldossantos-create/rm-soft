"""stock lots (lote / validade)

The stock of a product followed by lot / expiry, per warehouse (stock_lots), which lots each ledger row moved
(stock_movement_lots), the lot on entry lines; the product's single "Data limite de consumo" goes.

Revision ID: d3a6b1250t82
Revises: c2f5a0149s71
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "d3a6b1250t82"
down_revision = "c2f5a0149s71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_lots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False, index=True),
        sa.Column("warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False, index=True),
        sa.Column("lot_number", sa.String(60), nullable=True),
        sa.Column("expiry_date", sa.Date, nullable=True, index=True),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "stock_movement_lots",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("movement_id", UUID(as_uuid=True), sa.ForeignKey("stock_movements.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("lot_id", UUID(as_uuid=True), sa.ForeignKey("stock_lots.id"), nullable=False, index=True),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
    )
    op.add_column("stock_movement_document_lines", sa.Column("lot_number", sa.String(60), nullable=True))
    op.add_column("stock_movement_document_lines", sa.Column("expiry_date", sa.Date, nullable=True))
    op.add_column("stock_movement_document_lines", sa.Column("lot_id", UUID(as_uuid=True), sa.ForeignKey("stock_lots.id"), nullable=True))
    op.add_column("purchase_invoice_lines", sa.Column("lot_number", sa.String(60), nullable=True))
    op.add_column("purchase_invoice_lines", sa.Column("expiry_date", sa.Date, nullable=True))
    # a product already marked as followed keeps its stock: one "Sem lote" lot per warehouse holding some, so the
    # lots add up to the stock from the start
    op.execute("""
        INSERT INTO stock_lots (id, company_id, product_id, warehouse_id, lot_number, expiry_date, quantity, created_at)
        SELECT gen_random_uuid(), s.company_id, s.product_id, s.warehouse_id, NULL, NULL, s.quantity, now()
        FROM stock s JOIN products p ON p.id = s.product_id
        WHERE s.quantity > 0 AND p.managed_by_stock AND (p.managed_by_batch OR p.managed_by_expiry)
    """)
    op.drop_column("products", "expiry_date")


def downgrade() -> None:
    op.add_column("products", sa.Column("expiry_date", sa.Date, nullable=True))
    op.drop_column("purchase_invoice_lines", "expiry_date")
    op.drop_column("purchase_invoice_lines", "lot_number")
    op.drop_column("stock_movement_document_lines", "lot_id")
    op.drop_column("stock_movement_document_lines", "expiry_date")
    op.drop_column("stock_movement_document_lines", "lot_number")
    op.drop_table("stock_movement_lots")
    op.drop_table("stock_lots")
