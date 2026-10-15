"""guias (GR, GT, GD): the documents that travel with the goods (SAF-T MovementOfGoods); the catalog: GR and GT are
issued documents (fiscal, invoicing area), GD added, AC deactivated

Revision ID: z5c2d7e16p48
Revises: y4b1c6d05o37
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "z5c2d7e16p48"
down_revision = "y4b1c6d05o37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("EMITIDA", "FATURADA", "ANULADA", name="goodsmovementstatus")
    op.create_table(
        "goods_movements",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("document_type_id", UUID(as_uuid=True), sa.ForeignKey("document_types.id"), nullable=False),
        sa.Column("movement_type", sa.String(2), nullable=False),
        sa.Column("series", sa.String(30), nullable=False),
        sa.Column("number", sa.Integer, nullable=False),
        sa.Column("fiscal_period_id", UUID(as_uuid=True), sa.ForeignKey("fiscal_periods.id"), nullable=False, index=True),
        sa.Column("movement_date", sa.Date, nullable=False),
        sa.Column("start_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("customer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=True, index=True),
        sa.Column("supplier_id", UUID(as_uuid=True), sa.ForeignKey("suppliers.id"), nullable=True, index=True),
        sa.Column("purchase_invoice_id", UUID(as_uuid=True), sa.ForeignKey("purchase_invoices.id"), nullable=True),
        sa.Column("origin_warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=False),
        sa.Column("destination_warehouse_id", UUID(as_uuid=True), sa.ForeignKey("warehouses.id"), nullable=True),
        sa.Column("load_address", sa.String(250), nullable=False),
        sa.Column("unload_address", sa.String(250), nullable=False),
        sa.Column("vehicle_plate", sa.String(20), nullable=True),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("net_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("gross_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("atcud", sa.String(50), nullable=False),
        sa.Column("document_hash", sa.String(255), nullable=False),
        sa.Column("status", status, nullable=False),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "document_type_id", "series", "number", name="uq_goods_movement_number"),
    )
    op.create_table(
        "goods_movement_lines",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("goods_movement_id", UUID(as_uuid=True), sa.ForeignKey("goods_movements.id"), nullable=False, index=True),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("product_id", UUID(as_uuid=True), sa.ForeignKey("products.id"), nullable=False),
        sa.Column("product_code", sa.String(50), nullable=False),
        sa.Column("description", sa.String(255), nullable=False),
        sa.Column("sale_unit_id", UUID(as_uuid=True), sa.ForeignKey("product_sale_units.id"), nullable=True),
        sa.Column("unit_code", sa.String(20), nullable=True),
        sa.Column("unit_factor", sa.Numeric(14, 4), nullable=False, server_default="1"),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("vat_rate", sa.Numeric(5, 2), nullable=False),
        sa.Column("tax_code", sa.String(3), nullable=False),
        sa.Column("exemption_code", sa.String(3), nullable=True),
        sa.Column("exemption_reason", sa.String(255), nullable=True),
        sa.Column("line_net", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_vat", sa.Numeric(14, 2), nullable=False),
    )

    # The catalog: GR and GT are documents the company issues (hash, series, SAF-T MovementOfGoods) - not purchases;
    # GD (returns to a supplier) is added; AC (aviso de cobrança) is not used yet.
    op.execute("""UPDATE document_types SET area = 'FACTURACAO', is_fiscal = true, saft_section = 'MOVEMENTS',
                  deducts_stock = true WHERE code IN ('GR', 'GT')""")
    op.execute("""
        INSERT INTO document_types (id, code, area, electronic_eligible, is_fiscal, name, description, is_active,
            rules_locked, saft_section, revenue_sign, requires_origin, has_lines, paid_on_issue, sent_to_agt,
            deducts_stock, accepts_credit_note, accepts_debit_note, accepts_receipt, convertible, issuable_in_invoices,
            issuable_at_pos, requires_payment_term, requires_customer)
        SELECT gen_random_uuid(), 'GD', 'FACTURACAO', false, true, 'Guia de Devolução',
            'Devolução de mercadoria ao fornecedor', true, false, 'MOVEMENTS', 0, false, true, false, false,
            true, false, false, false, false, false, false, false, false
        WHERE NOT EXISTS (SELECT 1 FROM document_types WHERE code = 'GD')
    """)
    op.execute("UPDATE document_types SET is_active = false WHERE code = 'AC'")


def downgrade() -> None:
    op.execute("UPDATE document_types SET is_active = true WHERE code = 'AC'")
    op.execute("DELETE FROM document_types WHERE code = 'GD' AND NOT EXISTS (SELECT 1 FROM document_series s WHERE s.document_type_id = document_types.id)")
    op.execute("UPDATE document_types SET area = 'COMPRAS', is_fiscal = false, saft_section = 'NONE', deducts_stock = false WHERE code IN ('GR', 'GT')")
    op.drop_table("goods_movement_lines")
    op.drop_table("goods_movements")
    sa.Enum(name="goodsmovementstatus").drop(op.get_bind(), checkfirst=True)
