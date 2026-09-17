"""add cash_offices table

Revision ID: ee3855aeebb7
Revises: eb44a60d2a44
Create Date: 2026-09-08 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "ee3855aeebb7"
down_revision: Union[str, None] = "eb44a60d2a44"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ### schema: cash_offices table ###
    op.create_table(
        "cash_offices",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("company_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("billetage_enabled", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_cash_offices_company_id"), "cash_offices", ["company_id"], unique=False)

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index
    # (lower(name)) not represented in the SQLAlchemy Company model, so
    # autogenerate flagged it as "removed" by mistake - intentionally NOT
    # touched here, same as in the points_of_sale migration.

    # ### data: backfill - one default CashOffice per existing Company ###
    connection = op.get_bind()

    companies = connection.execute(sa.text("SELECT id FROM companies")).fetchall()
    for (company_id,) in companies:
        connection.execute(
            sa.text(
                "INSERT INTO cash_offices (id, company_id, name, billetage_enabled, is_active, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :company_id, 'Caixa Geral', false, true, now(), now())"
            ),
            {"company_id": company_id},
        )


def downgrade() -> None:
    op.drop_index(op.f("ix_cash_offices_company_id"), table_name="cash_offices")
    op.drop_table("cash_offices")
