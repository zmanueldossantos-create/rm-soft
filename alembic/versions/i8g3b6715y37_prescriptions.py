"""pharmacy: prescriptions (receitas) of the sales and the company's prescription policy

Revision ID: i8g3b6715y37
Revises: h7f2a5604x26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "i8g3b6715y37"
down_revision = "h7f2a5604x26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prescriptions",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False, unique=True),
        sa.Column("number", sa.String(50), nullable=True),
        sa.Column("prescriber", sa.String(150), nullable=True),
        sa.Column("health_unit", sa.String(150), nullable=True),
        sa.Column("patient_name", sa.String(150), nullable=True),
        sa.Column("patient_document", sa.String(50), nullable=True),
        sa.Column("is_special", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.add_column("companies", sa.Column("prescription_policy", sa.String(20), nullable=False, server_default="OBRIGATORIA"))


def downgrade() -> None:
    op.drop_column("companies", "prescription_policy")
    op.drop_table("prescriptions")
