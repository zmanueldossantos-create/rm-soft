"""Tesouraria - transfers between two bank accounts of the company: immediate within one bank, em trânsito between
two banks until the funds are confirmed available.

Revision ID: c6a9t3n71s03
Revises: b5z8s2m60r92
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "c6a9t3n71s03"
down_revision = "b5z8s2m60r92"
branch_labels = None
depends_on = None


def upgrade() -> None:
    status = postgresql.ENUM("EM_TRANSITO", "DISPONIVEL", "ANULADO", name="banktransferstatus")
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "bank_transfers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("series", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("from_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_bank_accounts.id"), nullable=False, index=True),
        sa.Column("to_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_bank_accounts.id"), nullable=False, index=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("transfer_date", sa.Date(), nullable=False),
        sa.Column("available_date", sa.Date(), nullable=True),
        sa.Column("status", postgresql.ENUM("EM_TRANSITO", "DISPONIVEL", "ANULADO", name="banktransferstatus", create_type=False), nullable=False),
        sa.Column("reference", sa.String(60), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("confirmed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "series", "number", name="uq_bank_transfer_number"),
    )


def downgrade() -> None:
    op.drop_table("bank_transfers")
    postgresql.ENUM(name="banktransferstatus").drop(op.get_bind(), checkfirst=True)
