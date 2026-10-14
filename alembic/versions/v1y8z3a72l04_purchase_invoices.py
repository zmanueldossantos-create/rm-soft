"""purchases: supplier country and trade name, the deductible VAT of each regime, purchase invoices

Revision ID: v1y8z3a72l04
Revises: u0x7y2z61k93
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "v1y8z3a72l04"
down_revision = "u0x7y2z61k93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("trade_name", sa.String(255), nullable=True))
    op.add_column("suppliers", sa.Column("country_id", UUID(as_uuid=True), sa.ForeignKey("countries.id"), nullable=True))

    op.add_column("fiscal_regimes", sa.Column("input_vat_deductible_pct", sa.Numeric(5, 2), server_default="100", nullable=False))
    # the starting values of the existing regimes (then managed by SUPER_ADMIN): Simplificado 7 %, Exclusão 0 %
    op.execute("UPDATE fiscal_regimes SET input_vat_deductible_pct = 7 WHERE name ILIKE '%simplific%'")
    op.execute("UPDATE fiscal_regimes SET input_vat_deductible_pct = 0 WHERE name ILIKE '%exclus%'")

    status = sa.Enum("REGISTADA", "ANULADA", name="purchaseinvoicestatus")
    op.create_table(
        "purchase_invoices",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), sa.ForeignKey("fiscal_periods.id"), nullable=False),
        sa.Column("series", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("supplier_document", sa.String(60), nullable=False),
        sa.Column("document_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("deductible_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("vat_deductible", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_non_deductible", sa.Numeric(14, 2), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    for column in ("company_id", "supplier_id", "fiscal_period_id"):
        op.create_index(f"ix_purchase_invoices_{column}", "purchase_invoices", [column])
    op.create_table(
        "purchase_invoice_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("purchase_invoice_id", UUID(as_uuid=True), sa.ForeignKey("purchase_invoices.id"), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=True),
        sa.Column("service_id", UUID(as_uuid=True), sa.ForeignKey("services.id"), nullable=True),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 4), nullable=False),
        sa.Column("legal_vat_rate_id", UUID(as_uuid=True), sa.ForeignKey("legal_vat_rates.id"), nullable=False),
        sa.Column("tax_category", sa.String(3), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("exemption_id", UUID(as_uuid=True), sa.ForeignKey("vat_codes.id"), nullable=True),
        sa.Column("line_subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_vat", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_deductible", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_non_deductible", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_purchase_invoice_lines_purchase_invoice_id", "purchase_invoice_lines", ["purchase_invoice_id"])


def downgrade() -> None:
    op.drop_index("ix_purchase_invoice_lines_purchase_invoice_id", table_name="purchase_invoice_lines")
    op.drop_table("purchase_invoice_lines")
    for column in ("company_id", "supplier_id", "fiscal_period_id"):
        op.drop_index(f"ix_purchase_invoices_{column}", table_name="purchase_invoices")
    op.drop_table("purchase_invoices")
    sa.Enum(name="purchaseinvoicestatus").drop(op.get_bind(), checkfirst=True)
    op.drop_column("fiscal_regimes", "input_vat_deductible_pct")
    op.drop_column("suppliers", "country_id")
    op.drop_column("suppliers", "trade_name")
