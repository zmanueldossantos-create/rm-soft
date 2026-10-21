"""users.password_changed_at (a password change ends the account's other sessions)

Revision ID: r8p2k5604h26
Revises: q7o1j4593g15
"""
import sqlalchemy as sa
from alembic import op

revision = "r8p2k5604h26"
down_revision = "q7o1j4593g15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_changed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "password_changed_at")
