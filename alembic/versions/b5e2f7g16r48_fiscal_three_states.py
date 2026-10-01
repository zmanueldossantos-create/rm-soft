"""fiscal years and periods: three states (ABERTO, FECHO_PARCIAL, FECHADO) replace is_open

Revision ID: b5e2f7g16r48
Revises: z3c0d5e94p26
"""
from alembic import op
import sqlalchemy as sa

revision = "b5e2f7g16r48"
down_revision = "z3c0d5e94p26"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("fiscal_periods", "fiscal_years"):
        op.add_column(table, sa.Column("status", sa.String(15), nullable=False, server_default="ABERTO"))
        op.execute(f"UPDATE {table} SET status = CASE WHEN is_open THEN 'ABERTO' ELSE 'FECHADO' END")
        op.drop_column(table, "is_open")


def downgrade() -> None:
    for table in ("fiscal_periods", "fiscal_years"):
        op.add_column(table, sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()))
        op.execute(f"UPDATE {table} SET is_open = (status = 'ABERTO')")
        op.drop_column(table, "status")
