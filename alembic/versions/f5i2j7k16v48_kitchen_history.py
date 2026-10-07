"""cuisine : qui et quand a chaque etape d'un plat (debut, pronto, annulation) - historique de la cuisine

Revision ID: f5i2j7k16v48
Revises: e4h1i6j05u37
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "f5i2j7k16v48"
down_revision = "e4h1i6j05u37"
branch_labels = None
depends_on = None

USER_COLUMNS = ("cancelled_by_user_id", "started_by_user_id", "ready_by_user_id")


def upgrade() -> None:
    op.add_column("open_account_lines", sa.Column("started_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("open_account_lines", sa.Column("ready_at", sa.DateTime(timezone=True), nullable=True))
    for column in USER_COLUMNS:
        op.add_column("open_account_lines", sa.Column(column, UUID(as_uuid=True), nullable=True))
        op.create_foreign_key(f"fk_open_account_lines_{column}", "open_account_lines", "users", [column], ["id"])


def downgrade() -> None:
    for column in USER_COLUMNS:
        op.drop_constraint(f"fk_open_account_lines_{column}", "open_account_lines", type_="foreignkey")
        op.drop_column("open_account_lines", column)
    op.drop_column("open_account_lines", "ready_at")
    op.drop_column("open_account_lines", "started_at")
