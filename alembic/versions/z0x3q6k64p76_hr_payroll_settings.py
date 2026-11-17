"""Recursos Humanos, step 2: the payroll settings - INSS rates, hours and days of a month, the IRT tables (valid from
a date), the rubricas (allowances and deductions: fixed, % of the salary, formula or typed each month; INSS / IRT
base, exempt limit) and the rubricas of each employee.

Revision ID: z0x3q6k64p76
Revises: y9w2p5j63o75
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z0x3q6k64p76"
down_revision = "y9w2p5j63o75"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payroll_settings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, unique=True),
        sa.Column("inss_employee_rate", sa.Numeric(5, 2), nullable=False, server_default="3"),
        sa.Column("inss_employer_rate", sa.Numeric(5, 2), nullable=False, server_default="8"),
        sa.Column("monthly_hours", sa.Numeric(6, 2), nullable=False, server_default="190.66"),
        sa.Column("monthly_days", sa.Numeric(5, 2), nullable=False, server_default="22"),
        sa.Column("inss_deducted_from_irt", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "irt_tables",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("brackets", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "valid_from", name="uq_irt_tables_valid_from"),
    )
    op.create_index("ix_irt_tables_company_id", "irt_tables", ["company_id"])
    op.create_table(
        "payroll_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("nature", sa.String(10), nullable=False),
        sa.Column("calc_method", sa.String(12), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate", sa.Numeric(7, 3), nullable=True),
        sa.Column("formula", sa.Text(), nullable=True),
        sa.Column("formula_ast", postgresql.JSONB(), nullable=True),
        sa.Column("subject_inss", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("subject_irt", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("irt_exempt_limit", sa.Numeric(14, 2), nullable=True),
        sa.Column("applies_to_all", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_payroll_items_company_id", "payroll_items", ["company_id"])
    op.execute("CREATE UNIQUE INDEX uq_payroll_items_code ON payroll_items (company_id, upper(code))")
    op.create_table(
        "employee_payroll_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("item_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payroll_items.id"), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=True),
        sa.Column("rate", sa.Numeric(7, 3), nullable=True),
        sa.UniqueConstraint("employee_id", "item_id", name="uq_employee_payroll_item"),
    )
    op.create_index("ix_employee_payroll_items_company_id", "employee_payroll_items", ["company_id"])
    op.create_index("ix_employee_payroll_items_employee_id", "employee_payroll_items", ["employee_id"])


def downgrade() -> None:
    op.drop_table("employee_payroll_items")
    op.drop_table("payroll_items")
    op.drop_table("irt_tables")
    op.drop_table("payroll_settings")
