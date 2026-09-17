"""retire cash_offices, add points_of_sale.is_default

Revision ID: f3ec981688e8
Revises: d3a90de9c926
Create Date: 2026-09-08 15:14:12.405551

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "f3ec981688e8"
down_revision: Union[str, None] = "d3a90de9c926"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### drop FK constraints referencing cash_offices FIRST, before dropping the table itself ###
    op.drop_index("ix_cash_movements_destination_cash_office_id", table_name="cash_movements")
    op.drop_index("ix_cash_movements_source_cash_office_id", table_name="cash_movements")
    op.drop_constraint("cash_movements_source_cash_office_id_fkey", "cash_movements", type_="foreignkey")
    op.drop_constraint("cash_movements_destination_cash_office_id_fkey", "cash_movements", type_="foreignkey")
    op.drop_column("cash_movements", "source_cash_office_id")
    op.drop_column("cash_movements", "destination_cash_office_id")

    op.drop_index("ix_user_cash_point_access_cash_office_id", table_name="user_cash_point_access")
    op.drop_constraint("user_cash_point_access_cash_office_id_fkey", "user_cash_point_access", type_="foreignkey")
    op.drop_column("user_cash_point_access", "cash_office_id")

    # NOW cash_offices has no more dependents and can be dropped safely
    op.drop_index("ix_cash_offices_company_id", table_name="cash_offices")
    op.drop_table("cash_offices")

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here,
    # same as in prior migrations.

    # ### points_of_sale.is_default - added NULLABLE first, backfilled below, then locked NOT NULL ###
    op.add_column("points_of_sale", sa.Column("is_default", sa.Boolean(), nullable=True))

    # ### data: backfill - for each Activity, mark one existing POS as its default. ###
    # ### Prefers a POS literally named "<activity> - Caixa Geral" (the pattern used by ###
    # ### activity_service.create_activity going forward); falls back to the oldest POS ###
    # ### of that activity if no such name exists (covers POS created before this change). ###
    connection = op.get_bind()

    activities = connection.execute(sa.text("SELECT id, name FROM activities")).fetchall()
    for activity_id, activity_name in activities:
        expected_name = f"{activity_name} - Caixa Geral"
        default_pos = connection.execute(
            sa.text("SELECT id FROM points_of_sale WHERE activity_id = :activity_id AND name = :expected_name"),
            {"activity_id": activity_id, "expected_name": expected_name},
        ).fetchone()

        if default_pos is None:
            default_pos = connection.execute(
                sa.text(
                    "SELECT id FROM points_of_sale WHERE activity_id = :activity_id "
                    "ORDER BY created_at ASC LIMIT 1"
                ),
                {"activity_id": activity_id},
            ).fetchone()

        if default_pos is not None:
            connection.execute(
                sa.text("UPDATE points_of_sale SET is_default = true WHERE id = :pos_id"),
                {"pos_id": default_pos[0]},
            )

    # Any POS left NULL (e.g. an activity with zero POS, which shouldn't happen but just in
    # case) defaults to false before locking NOT NULL.
    connection.execute(sa.text("UPDATE points_of_sale SET is_default = false WHERE is_default IS NULL"))
    op.alter_column("points_of_sale", "is_default", nullable=False)

    # ### user_cash_point_access.pos_id -> NOT NULL (every remaining row already has one, ###
    # ### since cash_office-only rows would have failed the model's old CHECK constraint) ###
    op.alter_column("user_cash_point_access", "pos_id", existing_type=sa.UUID(), nullable=False)


def downgrade() -> None:
    op.alter_column("user_cash_point_access", "pos_id", existing_type=sa.UUID(), nullable=True)

    op.drop_column("points_of_sale", "is_default")

    op.create_table(
        "cash_offices",
        sa.Column("id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("company_id", sa.UUID(), autoincrement=False, nullable=False),
        sa.Column("name", sa.VARCHAR(length=100), autoincrement=False, nullable=False),
        sa.Column("billetage_enabled", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("is_active", sa.BOOLEAN(), autoincrement=False, nullable=False),
        sa.Column("created_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), autoincrement=False, nullable=False),
        sa.Column("updated_at", postgresql.TIMESTAMP(timezone=True), server_default=sa.text("now()"), autoincrement=False, nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], name="cash_offices_company_id_fkey"),
        sa.PrimaryKeyConstraint("id", name="cash_offices_pkey"),
    )
    op.create_index("ix_cash_offices_company_id", "cash_offices", ["company_id"], unique=False)

    op.add_column("user_cash_point_access", sa.Column("cash_office_id", sa.UUID(), autoincrement=False, nullable=True))
    op.create_foreign_key("user_cash_point_access_cash_office_id_fkey", "user_cash_point_access", "cash_offices", ["cash_office_id"], ["id"])
    op.create_index("ix_user_cash_point_access_cash_office_id", "user_cash_point_access", ["cash_office_id"], unique=False)

    op.add_column("cash_movements", sa.Column("destination_cash_office_id", sa.UUID(), autoincrement=False, nullable=True))
    op.add_column("cash_movements", sa.Column("source_cash_office_id", sa.UUID(), autoincrement=False, nullable=True))
    op.create_foreign_key("cash_movements_destination_cash_office_id_fkey", "cash_movements", "cash_offices", ["destination_cash_office_id"], ["id"])
    op.create_foreign_key("cash_movements_source_cash_office_id_fkey", "cash_movements", "cash_offices", ["source_cash_office_id"], ["id"])
    op.create_index("ix_cash_movements_source_cash_office_id", "cash_movements", ["source_cash_office_id"], unique=False)
    op.create_index("ix_cash_movements_destination_cash_office_id", "cash_movements", ["destination_cash_office_id"], unique=False)
