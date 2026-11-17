"""Recursos Humanos (capability HR), step 1: the role RH, the company's HR tables (departments, categories, job titles,
contract types, schedules, education levels, document types) and the employees' files.

Revision ID: x8v1o4i62n74
Revises: w7u0n3h61m73
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "x8v1o4i62n74"
down_revision = "w7u0n3h61m73"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # a new enum value must be committed before it is used
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'RH'")

    op.create_table(
        "hr_references",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_hr_references_company_id", "hr_references", ["company_id"])
    op.execute("CREATE UNIQUE INDEX uq_hr_references_name ON hr_references (company_id, kind, lower(name))")

    ref = lambda name: sa.Column(name, postgresql.UUID(as_uuid=True), sa.ForeignKey("hr_references.id"), nullable=True)  # noqa: E731
    op.create_table(
        "employees",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("number", sa.String(20), nullable=False),
        sa.Column("full_name", sa.String(200), nullable=False),
        sa.Column("gender", sa.String(1), nullable=True),
        sa.Column("birth_date", sa.Date(), nullable=True),
        sa.Column("marital_status", sa.String(12), nullable=True),
        sa.Column("nationality_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("countries.id"), nullable=True),
        sa.Column("father_name", sa.String(200), nullable=True),
        sa.Column("mother_name", sa.String(200), nullable=True),
        sa.Column("id_document_type", sa.String(20), nullable=True),
        sa.Column("id_document_number", sa.String(30), nullable=True),
        sa.Column("id_issued_on", sa.Date(), nullable=True),
        sa.Column("id_expires_on", sa.Date(), nullable=True),
        sa.Column("nif", sa.String(20), nullable=True),
        sa.Column("social_security_number", sa.String(20), nullable=True),
        sa.Column("address", sa.String(300), nullable=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("email", sa.String(120), nullable=True),
        ref("department_id"), ref("category_id"), ref("job_title_id"),
        sa.Column("establishment_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("establishments.id"), nullable=True),
        sa.Column("hired_on", sa.Date(), nullable=False),
        ref("contract_type_id"),
        sa.Column("contract_ends_on", sa.Date(), nullable=True),
        sa.Column("probation_ends_on", sa.Date(), nullable=True),
        ref("work_schedule_id"),
        sa.Column("base_salary", sa.Numeric(14, 2), nullable=False),
        sa.Column("payment_method", sa.String(15), nullable=False, server_default="TRANSFERENCIA"),
        sa.Column("bank_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("banks.id"), nullable=True),
        sa.Column("iban", sa.String(34), nullable=True),
        ref("education_level_id"),
        sa.Column("training", sa.Text(), nullable=True),
        sa.Column("experience", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("left_on", sa.Date(), nullable=True),
        sa.Column("leaving_reason", sa.String(25), nullable=True),
        sa.Column("leaving_note", sa.String(300), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_employees_company_id", "employees", ["company_id"])
    op.execute("CREATE UNIQUE INDEX uq_employees_number ON employees (company_id, lower(number))")
    op.execute("CREATE UNIQUE INDEX uq_employees_id_document ON employees (company_id, lower(id_document_number)) "
               "WHERE id_document_number IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_employees_nif ON employees (company_id, lower(nif)) WHERE nif IS NOT NULL")
    op.execute("CREATE UNIQUE INDEX uq_employees_social_security ON employees (company_id, social_security_number) "
               "WHERE social_security_number IS NOT NULL")


def downgrade() -> None:
    bind = op.get_bind()
    n = bind.execute(sa.text("SELECT count(*) FROM users WHERE role = 'RH'")).scalar()
    if n:
        raise RuntimeError(f"{n} utilizador(es) ainda têm o papel RH: mude o papel antes.")
    bind.execute(sa.text("DELETE FROM role_permissions WHERE role = 'RH'"))
    op.drop_table("employees")
    op.drop_table("hr_references")
