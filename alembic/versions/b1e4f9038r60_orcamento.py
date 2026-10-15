"""orçamento (OR): a quote with a validity date - a working document like the pro-forma (SAF-T WorkingDocuments,
WorkType OR), issued from Faturas with a customer, convertible into a FT / FR

Revision ID: b1e4f9038r60
Revises: a0d3e8f27q59
"""
import sqlalchemy as sa
from alembic import op

revision = "b1e4f9038r60"
down_revision = "a0d3e8f27q59"
branch_labels = None
depends_on = None

# the rules of the OR (read by the tests' catalog too - tests/conftest.py)
RULES_OVERRIDES = {"OR": {
    "saft_section": "WORKING", "revenue_sign": 0, "requires_origin": False, "has_lines": True, "paid_on_issue": False,
    "sent_to_agt": False, "deducts_stock": False, "accepts_credit_note": False, "accepts_debit_note": False,
    "accepts_receipt": False, "convertible": True, "issuable_in_invoices": True, "issuable_at_pos": False,
    "requires_payment_term": False, "requires_customer": True,
}}


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE invoicetype ADD VALUE IF NOT EXISTS 'ORCAMENTO'")
    op.add_column("invoices", sa.Column("valid_until", sa.Date(), nullable=True))
    # the catalog's OR: a non-fiscal working document (the pro-forma's rules), with a customer, from Faturas only
    op.execute("""
        INSERT INTO document_types (id, code, name, area, is_fiscal, is_active, electronic_eligible, rules_locked,
                                    saft_section, revenue_sign, requires_origin, has_lines, paid_on_issue, sent_to_agt,
                                    deducts_stock, accepts_credit_note, accepts_debit_note, accepts_receipt, convertible,
                                    issuable_in_invoices, issuable_at_pos, requires_payment_term, requires_customer)
        SELECT gen_random_uuid(), 'OR', 'Orçamento', 'FACTURACAO', false, true, false, false, 'NONE', 0, false, true,
               false, false, false, false, false, false, false, false, false, false, false
        WHERE NOT EXISTS (SELECT 1 FROM document_types WHERE code = 'OR')
    """)
    op.execute("""
        UPDATE document_types SET name = 'Orçamento', area = 'FACTURACAO', is_fiscal = false, is_active = true,
               saft_section = 'WORKING', revenue_sign = 0, requires_origin = false, has_lines = true,
               paid_on_issue = false, sent_to_agt = false, deducts_stock = false, accepts_credit_note = false,
               accepts_debit_note = false, accepts_receipt = false, convertible = true, issuable_in_invoices = true,
               issuable_at_pos = false, requires_payment_term = false, requires_customer = true,
               description = COALESCE(description, 'Proposta de preços com validade - passa a FT ou FR')
        WHERE code = 'OR'
    """)


def downgrade() -> None:
    op.execute("UPDATE document_types SET saft_section = 'NONE', convertible = false, issuable_in_invoices = false, "
               "requires_customer = false WHERE code = 'OR'")
    op.drop_column("invoices", "valid_until")
    # the enum value stays: PostgreSQL cannot remove it
