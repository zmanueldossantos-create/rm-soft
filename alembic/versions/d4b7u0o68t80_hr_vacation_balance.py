"""Recursos Humanos, step 3d: the holiday balance - the company's rules (days a year, days per month in the year of
the admission, days carried to the next year, a request beyond the balance allowed or not) and the corrections of an
employee's balance.

Revision ID: d4b7u0o68t80
Revises: c3a6t9n67s79
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4b7u0o68t80"
down_revision = "c3a6t9n67s79"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_settings", sa.Column("vacation_days_year", sa.Numeric(5, 1), nullable=False, server_default="22"))
    op.add_column("payroll_settings", sa.Column("vacation_days_per_month_first_year", sa.Numeric(4, 2), nullable=False, server_default="2"))
    op.add_column("payroll_settings", sa.Column("vacation_carry_max", sa.Numeric(5, 1), nullable=True))
    op.add_column("payroll_settings", sa.Column("vacation_allow_negative", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("payroll_settings", sa.Column("vacation_start_year", sa.Integer(), nullable=True))
    # the companies already set up start counting this year (the years before RM SOFT are not followed)
    op.execute("UPDATE payroll_settings SET vacation_start_year = EXTRACT(YEAR FROM now())::int")
    op.create_table(
        "hr_vacation_adjustments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("days", sa.Numeric(6, 1), nullable=False),
        sa.Column("note", sa.String(300), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_hr_vacation_adjustments_company_id", "hr_vacation_adjustments", ["company_id"])
    op.create_index("ix_hr_vacation_adjustments_employee_id", "hr_vacation_adjustments", ["employee_id"])


def downgrade() -> None:
    op.drop_table("hr_vacation_adjustments")
    for column in ("vacation_start_year", "vacation_allow_negative", "vacation_carry_max", "vacation_days_per_month_first_year", "vacation_days_year"):
        op.drop_column("payroll_settings", column)
