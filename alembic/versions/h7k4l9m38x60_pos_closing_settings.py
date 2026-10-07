"""pos closing settings: accept a difference at closing, propose the closing report

Revision ID: h7k4l9m38x60
Revises: g6j3k8l27w59
"""
from alembic import op
import sqlalchemy as sa

revision = "h7k4l9m38x60"
down_revision = "g6j3k8l27w59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # every existing till keeps today's behaviour: a difference is accepted, with a reason
    op.add_column("points_of_sale", sa.Column("accept_closing_difference", sa.Boolean(), server_default=sa.true(), nullable=False))
    op.add_column("points_of_sale", sa.Column("print_closing_report", sa.Boolean(), server_default=sa.false(), nullable=False))


def downgrade() -> None:
    op.drop_column("points_of_sale", "print_closing_report")
    op.drop_column("points_of_sale", "accept_closing_difference")
