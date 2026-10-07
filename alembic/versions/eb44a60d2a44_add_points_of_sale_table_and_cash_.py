"""add points_of_sale table and cash_sessions.pos_id

Revision ID: eb44a60d2a44
Revises: e8f69cea69d6
Create Date: 2026-09-07 18:56:41.253811

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "eb44a60d2a44"
down_revision: Union[str, None] = "e8f69cea69d6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### schema: points_of_sale table ###
    op.create_table(
        "points_of_sale",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("activity_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["activity_id"], ["activities.id"]),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("activity_id", "name", name="uq_pos_activity_name"),
    )
    op.create_index(op.f("ix_points_of_sale_activity_id"), "points_of_sale", ["activity_id"], unique=False)
    op.create_index(op.f("ix_points_of_sale_company_id"), "points_of_sale", ["company_id"], unique=False)

    # ### schema: cash_sessions.pos_id - added NULLABLE first, backfilled below, then locked NOT NULL ###
    op.add_column("cash_sessions", sa.Column("pos_id", sa.UUID(), nullable=True))
    op.create_index(op.f("ix_cash_sessions_pos_id"), "cash_sessions", ["pos_id"], unique=False)
    op.create_foreign_key(None, "cash_sessions", "points_of_sale", ["pos_id"], ["id"])

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index
    # (lower(name)) not represented in the SQLAlchemy Company model, so
    # autogenerate flagged it as "removed" by mistake - intentionally NOT
    # touched here, it must keep protecting case-insensitive company names.

    # ### data: backfill - one default PointOfSale per existing Activity, ###
    # ### then attach every existing CashSession to its activity's new POS ###
    connection = op.get_bind()

    activities = connection.execute(sa.text("SELECT id, company_id, name FROM activities")).fetchall()
    for activity_id, company_id, activity_name in activities:
        pos_id = connection.execute(
            sa.text(
                "INSERT INTO points_of_sale (id, company_id, activity_id, name, is_active, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :company_id, :activity_id, :name, true, now(), now()) "
                "RETURNING id"
            ),
            {"company_id": company_id, "activity_id": activity_id, "name": activity_name},
        ).scalar_one()

        connection.execute(
            sa.text("UPDATE cash_sessions SET pos_id = :pos_id WHERE activity_id = :activity_id"),
            {"pos_id": pos_id, "activity_id": activity_id},
        )

    # ### schema: now that every row has a pos_id, lock the column NOT NULL ###
    op.alter_column("cash_sessions", "pos_id", nullable=False)


def downgrade() -> None:
    op.alter_column("cash_sessions", "pos_id", nullable=True)
    op.drop_constraint(None, "cash_sessions", type_="foreignkey")
    op.drop_index(op.f("ix_cash_sessions_pos_id"), table_name="cash_sessions")
    op.drop_column("cash_sessions", "pos_id")
    op.drop_index(op.f("ix_points_of_sale_company_id"), table_name="points_of_sale")
    op.drop_index(op.f("ix_points_of_sale_activity_id"), table_name="points_of_sale")
    op.drop_table("points_of_sale")
