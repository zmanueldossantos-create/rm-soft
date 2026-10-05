"""printing after a sale moves from the activity to the till (point of sale): two tills of one activity may differ

Revision ID: y8b5c0d49o71
Revises: x7a4b9c38n60
"""
from alembic import op
import sqlalchemy as sa

revision = "y8b5c0d49o71"
down_revision = "x7a4b9c38n60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("activities", "print_a4")
    op.drop_column("activities", "print_ticket")
    op.drop_column("activities", "print_after_sale")
    op.add_column("points_of_sale", sa.Column("print_after_sale", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("points_of_sale", sa.Column("print_ticket", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("points_of_sale", sa.Column("print_a4", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("points_of_sale", "print_a4")
    op.drop_column("points_of_sale", "print_ticket")
    op.drop_column("points_of_sale", "print_after_sale")
    op.add_column("activities", sa.Column("print_after_sale", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("activities", sa.Column("print_ticket", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("activities", sa.Column("print_a4", sa.Boolean(), server_default=sa.false(), nullable=False))
