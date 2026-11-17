"""Recursos Humanos, step 3a / 3b: the working days of the week, the holidays (national, pontes, tolerances, local)
and the absence types (category, paid, takes holiday days, working or calendar days, max days, document required).

Revision ID: a1y4r7l65q77
Revises: z0x3q6k64p76
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a1y4r7l65q77"
down_revision = "z0x3q6k64p76"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("payroll_settings", sa.Column("work_weekdays", postgresql.JSONB(), nullable=False,
                                                server_default=sa.text("'[0, 1, 2, 3, 4]'::jsonb")))
    op.create_table(
        "hr_holidays",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False, server_default="FERIADO"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "day", name="uq_hr_holidays_day"),
    )
    op.create_index("ix_hr_holidays_company_id", "hr_holidays", ["company_id"])
    op.create_table(
        "hr_absence_types",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(15), nullable=False),
        sa.Column("paid", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("takes_holiday_days", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("working_days", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("max_days", sa.Integer(), nullable=True),
        sa.Column("requires_document", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("notes", sa.String(300), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_hr_absence_types_company_id", "hr_absence_types", ["company_id"])


def downgrade() -> None:
    op.drop_table("hr_absence_types")
    op.drop_table("hr_holidays")
    op.drop_column("payroll_settings", "work_weekdays")
