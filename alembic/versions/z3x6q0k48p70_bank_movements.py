"""Tesouraria - the reasons say where they are used (the tills, the bank accounts, or both: existing ones stay for the
tills), and the bank accounts get their own typed movements (bank fees, a capital entry...), never deleted - cancelled.

Revision ID: z3x6q0k48p70
Revises: y2w5p9j37o69
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "z3x6q0k48p70"
down_revision = "y2w5p9j37o69"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("cash_movement_reasons", sa.Column("for_cash", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("cash_movement_reasons", sa.Column("for_bank", sa.Boolean(), nullable=False, server_default="false"))
    status = postgresql.ENUM("REGISTADO", "ANULADO", name="bankmovementstatus")
    status.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "bank_movements",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_bank_accounts.id"), nullable=False, index=True),
        sa.Column("reason_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cash_movement_reasons.id"), nullable=False),
        sa.Column("direction", postgresql.ENUM("ENTRADA", "SAIDA", name="movementdirection", create_type=False), nullable=False),
        sa.Column("series", sa.String(20), nullable=False),
        sa.Column("number", sa.Integer(), nullable=False),
        sa.Column("movement_date", sa.Date(), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("reference", sa.String(60), nullable=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("status", postgresql.ENUM("REGISTADO", "ANULADO", name="bankmovementstatus", create_type=False), nullable=False),
        sa.Column("cancel_reason", sa.String(300), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "series", "number", name="uq_bank_movement_number"),
    )


def downgrade() -> None:
    op.drop_table("bank_movements")
    postgresql.ENUM(name="bankmovementstatus").drop(op.get_bind(), checkfirst=True)
    op.drop_column("cash_movement_reasons", "for_bank")
    op.drop_column("cash_movement_reasons", "for_cash")
