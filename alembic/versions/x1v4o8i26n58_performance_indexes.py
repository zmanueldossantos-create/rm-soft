"""Performance indexes: the article / document columns read by the reports, the Painel and the links between documents
(top products, a credit note's original, the stock of a product...), and the documents' lists by date - so a year of
sales (100 000 documents) is read through an index instead of the whole table.

Revision ID: x1v4o8i26n58
Revises: w9u3n7h15m47
"""
from alembic import op

revision = "x1v4o8i26n58"
down_revision = "w9u3n7h15m47"
branch_labels = None
depends_on = None

# (index name, table, columns) - the names SQLAlchemy gives to index=True / the models' Index()
INDEXES = (
    ("ix_invoice_lines_product_id", "invoice_lines", ["product_id"]),
    ("ix_invoice_lines_service_id", "invoice_lines", ["service_id"]),
    ("ix_invoices_reference_invoice_id", "invoices", ["reference_invoice_id"]),
    ("ix_invoices_company_created_at", "invoices", ["company_id", "created_at"]),
    ("ix_invoices_company_business_date", "invoices", ["company_id", "business_date"]),
    ("ix_goods_movement_lines_product_id", "goods_movement_lines", ["product_id"]),
    ("ix_goods_movements_invoice_id", "goods_movements", ["invoice_id"]),
    ("ix_purchase_invoice_lines_product_id", "purchase_invoice_lines", ["product_id"]),
    ("ix_open_account_lines_product_id", "open_account_lines", ["product_id"]),
    ("ix_products_category_id", "products", ["category_id"]),
    ("ix_bookings_invoice_id", "bookings", ["invoice_id"]),
    ("ix_open_accounts_invoice_id", "open_accounts", ["invoice_id"]),
    ("ix_stock_movement_document_lines_product_id", "stock_movement_document_lines", ["product_id"]),
)


def upgrade() -> None:
    for name, table, columns in INDEXES:
        op.create_index(name, table, columns, if_not_exists=True)


def downgrade() -> None:
    for name, table, _columns in reversed(INDEXES):
        op.drop_index(name, table_name=table, if_exists=True)
