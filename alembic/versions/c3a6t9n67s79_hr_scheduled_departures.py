"""Recursos Humanos: a departure registered for a day still to come is scheduled - the employee stays active until
that day is over. The employees taken out ahead of their day by the previous rule are put back in the active list
(their user account, closed then, is reopened by the gestor in Utilizadores).

Revision ID: c3a6t9n67s79
Revises: b2z5s8m66r78
"""
from alembic import op

revision = "c3a6t9n67s79"
down_revision = "b2z5s8m66r78"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE employees SET is_active = true WHERE is_active = false AND left_on > current_date")


def downgrade() -> None:
    pass
