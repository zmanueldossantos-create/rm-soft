"""Recursos Humanos, step 1 (continued): the employee's photo and the documents of his file (type, handed in on,
valid until, the scanned file - kept in the database, never public), and his user account (switched off when he
leaves).

Revision ID: y9w2p5j63o75
Revises: x8v1o4i62n74
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "y9w2p5j63o75"
down_revision = "x8v1o4i62n74"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("employees", sa.Column("user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.execute("CREATE UNIQUE INDEX uq_employees_user ON employees (user_id) WHERE user_id IS NOT NULL")
    op.create_table(
        "employee_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("employee_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("employees.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("document_type_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("hr_references.id"), nullable=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column("delivered_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("file_name", sa.String(200), nullable=True),
        sa.Column("content_type", sa.String(60), nullable=True),
        sa.Column("size", sa.Integer(), nullable=True),
        sa.Column("content", sa.LargeBinary(), nullable=True),
        sa.Column("uploaded_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_employee_files_company_id", "employee_files", ["company_id"])
    op.create_index("ix_employee_files_employee_id", "employee_files", ["employee_id"])


def downgrade() -> None:
    op.drop_table("employee_files")
    op.execute("DROP INDEX IF EXISTS uq_employees_user")
    op.drop_column("employees", "user_id")
