"""add cash movement reception status

Revision ID: debc6ed7cbd5
Revises: 99238d553718
Create Date: 2026-09-11 10:52:53.611168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "debc6ed7cbd5"
down_revision: Union[str, None] = "99238d553718"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # status added nullable first, backfilled, then locked NOT NULL - existing
    # movements (all created before this two-step flow existed) are treated as
    # already RECEBIDO, matching the old behavior where they counted immediately.
    # The PostgreSQL enum type must be created explicitly first - op.add_column
    # with sa.Enum(...) does not auto-create the underlying type (unlike create_table).
    cash_movement_status_enum = sa.Enum("PENDENTE", "RECEBIDO", name="cashmovementstatus")
    cash_movement_status_enum.create(op.get_bind())
    op.add_column("cash_movements", sa.Column("status", cash_movement_status_enum, nullable=True))
    op.add_column("cash_movements", sa.Column("received_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("cash_movements", sa.Column("received_by_user_id", sa.UUID(), nullable=True))
    op.create_foreign_key(None, "cash_movements", "users", ["received_by_user_id"], ["id"])

    connection = op.get_bind()
    connection.execute(sa.text(
        "UPDATE cash_movements SET status = 'RECEBIDO', received_at = created_at, received_by_user_id = created_by_user_id "
        "WHERE status IS NULL"
    ))
    op.alter_column("cash_movements", "status", existing_type=sa.Enum("PENDENTE", "RECEBIDO", name="cashmovementstatus"), nullable=False)

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.


def downgrade() -> None:
    op.drop_constraint(None, "cash_movements", type_="foreignkey")
    op.drop_column("cash_movements", "received_by_user_id")
    op.drop_column("cash_movements", "received_at")
    op.drop_column("cash_movements", "status")
