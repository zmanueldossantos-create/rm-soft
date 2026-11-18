"""Recursos Humanos, step 3c: the employees' absences (type, from / to, half a day, the days counted, reason,
justifying document, PEDIDA / APROVADA / RECUSADA / CANCELADA with who decided and when).

Revision ID: b2z5s8m66r78
Revises: a1y4r7l65q77
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "b2z5s8m66r78"
down_revision = "a1y4r7l65q77"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = sa.Enum("PEDIDA", "APROVADA", "RECUSADA", "CANCELADA", name="absence_status")
    op.create_table(
        "hr_absences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hr_absence_types.id"), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("half_day", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("days", sa.Numeric(6, 1), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employee_files.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", status, nullable=False, server_default="PEDIDA"),
        sa.Column("decision_note", sa.String(300), nullable=True),
        sa.Column("requested_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_hr_absences_company_id", "hr_absences", ["company_id"])
    op.create_index("ix_hr_absences_employee_id", "hr_absences", ["employee_id"])
    op.create_index("ix_hr_absences_start_date", "hr_absences", ["start_date"])
    op.create_index("ix_hr_absences_end_date", "hr_absences", ["end_date"])


def downgrade() -> None:
    op.drop_table("hr_absences")
    sa.Enum(name="absence_status").drop(op.get_bind(), checkfirst=True)
