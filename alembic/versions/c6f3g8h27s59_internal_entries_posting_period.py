"""internal entries booked in a fiscal period: fiscal_period_id on the stock ledger, movement documents and internal
consumptions; existing rows attached to the period of their month

Revision ID: c6f3g8h27s59
Revises: b5e2f7g16r48
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "c6f3g8h27s59"
down_revision = "b5e2f7g16r48"
branch_labels = None
depends_on = None

TABLES = {"stock_movements": "created_at", "stock_movement_documents": "movement_date", "internal_consumptions": "created_at"}


def upgrade() -> None:
    for table, date_column in TABLES.items():
        op.add_column(table, sa.Column("fiscal_period_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fiscal_periods.id"), nullable=True))
        op.create_index(f"ix_{table}_fiscal_period_id", table, ["fiscal_period_id"])
        op.execute(
            f"UPDATE {table} t SET fiscal_period_id = p.id FROM fiscal_periods p JOIN fiscal_years y ON y.id = p.fiscal_year_id "
            f"WHERE p.company_id = t.company_id AND y.year = EXTRACT(YEAR FROM t.{date_column}) AND p.month = EXTRACT(MONTH FROM t.{date_column})"
        )


def downgrade() -> None:
    for table in TABLES:
        op.drop_index(f"ix_{table}_fiscal_period_id", table_name=table)
        op.drop_column(table, "fiscal_period_id")
