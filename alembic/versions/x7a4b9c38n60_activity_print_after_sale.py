"""activities: printing after a sale at the till - off by default (nothing changes), then the ticket, the A4, or both
(the cashier picks one)

Revision ID: x7a4b9c38n60
Revises: w6z3a8b27m59
"""
from alembic import op
import sqlalchemy as sa

revision = "x7a4b9c38n60"
down_revision = "w6z3a8b27m59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("activities", sa.Column("print_after_sale", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("activities", sa.Column("print_ticket", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("activities", sa.Column("print_a4", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("activities", "print_a4")
    op.drop_column("activities", "print_ticket")
    op.drop_column("activities", "print_after_sale")
