"""invoice created_by_user_id - who created each document; existing ones get the user who opened their cash session

Revision ID: l1o8p3q72b04
Revises: k0n7o2p61a93
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "l1o8p3q72b04"
down_revision = "k0n7o2p61a93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("invoices_created_by_user_id_fkey", "invoices", "users", ["created_by_user_id"], ["id"])
    op.execute(
        "UPDATE invoices i SET created_by_user_id = s.opened_by_user_id "
        "FROM cash_sessions s WHERE s.id = i.cash_session_id AND i.created_by_user_id IS NULL"
    )


def downgrade() -> None:
    op.drop_constraint("invoices_created_by_user_id_fkey", "invoices", type_="foreignkey")
    op.drop_column("invoices", "created_by_user_id")
