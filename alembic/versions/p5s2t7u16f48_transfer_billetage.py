"""moedeiro: the notes and coins of a transfer between two tills - two count types and the count's transfer

Revision ID: p5s2t7u16f48
Revises: o4r1s6t05e37
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "p5s2t7u16f48"
down_revision = "o4r1s6t05e37"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE denominationcounttype ADD VALUE IF NOT EXISTS 'TRANSF_SAIDA'")
    op.execute("ALTER TYPE denominationcounttype ADD VALUE IF NOT EXISTS 'TRANSF_ENTRADA'")
    op.add_column("cash_denomination_counts", sa.Column("cash_movement_id", UUID(as_uuid=True), nullable=True))
    op.create_foreign_key("fk_cash_denomination_counts_cash_movement", "cash_denomination_counts", "cash_movements",
                          ["cash_movement_id"], ["id"])
    op.create_index("ix_cash_denomination_counts_cash_movement_id", "cash_denomination_counts", ["cash_movement_id"])


def downgrade() -> None:
    op.drop_index("ix_cash_denomination_counts_cash_movement_id", table_name="cash_denomination_counts")
    op.drop_constraint("fk_cash_denomination_counts_cash_movement", "cash_denomination_counts", type_="foreignkey")
    op.drop_column("cash_denomination_counts", "cash_movement_id")
    # the two enum values stay: PostgreSQL cannot remove an enum value
