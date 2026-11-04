"""Tesouraria - the payment terminals (TPA, Multicaixa Express): the bank account a card payment at the till lands
on, and the terminal each document was paid on.

Revision ID: a4y7r1l59q81
Revises: z3x6q0k48p70
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a4y7r1l59q81"
down_revision = "z3x6q0k48p70"
branch_labels = None
depends_on = None


def upgrade() -> None:
    kind = postgresql.ENUM("TPA", "EXPRESS", name="terminalkind")
    kind.create(op.get_bind(), checkfirst=True)
    op.create_table(
        "payment_terminals",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("kind", postgresql.ENUM("TPA", "EXPRESS", name="terminalkind", create_type=False), nullable=False),
        sa.Column("bank_account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("company_bank_accounts.id"), nullable=False, index=True),
        sa.Column("pos_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("points_of_sale.id"), nullable=True),
        sa.Column("payment_method_ids", postgresql.ARRAY(postgresql.UUID(as_uuid=True)), nullable=False, server_default="{}"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("company_id", "name", name="uq_payment_terminal_name"),
    )
    op.add_column("invoices", sa.Column("terminal_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("payment_terminals.id"), nullable=True))


def downgrade() -> None:
    op.drop_column("invoices", "terminal_id")
    op.drop_table("payment_terminals")
    postgresql.ENUM(name="terminalkind").drop(op.get_bind(), checkfirst=True)
