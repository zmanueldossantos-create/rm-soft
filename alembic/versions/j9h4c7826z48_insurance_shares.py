"""pharmacy: insurers (comparticipação) - the insurer fields of a customer and the shared sales

Revision ID: j9h4c7826z48
Revises: i8g3b6715y37
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "j9h4c7826z48"
down_revision = "i8g3b6715y37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("customers", sa.Column("is_insurer", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("customers", sa.Column("insurer_coverage_pct", sa.Numeric(5, 2), nullable=True))
    op.add_column("customers", sa.Column("insurer_medicines_only", sa.Boolean, nullable=False, server_default="true"))
    op.create_table(
        "insurance_shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("insurer_id", UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("patient_invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=True, unique=True),
        sa.Column("insurer_invoice_id", UUID(as_uuid=True), sa.ForeignKey("invoices.id"), nullable=False, unique=True),
        sa.Column("coverage_pct", sa.Numeric(5, 2), nullable=False),
        sa.Column("card_number", sa.String(60), nullable=False),
        sa.Column("beneficiary_name", sa.String(150), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("insurance_shares")
    op.drop_column("customers", "insurer_medicines_only")
    op.drop_column("customers", "insurer_coverage_pct")
    op.drop_column("customers", "is_insurer")
