"""move available_at_pos to per-company preference table

Revision ID: 99238d553718
Revises: 7e8e4a8a7cb8
Create Date: 2026-09-10 14:52:31.907906

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "99238d553718"
down_revision: Union[str, None] = "7e8e4a8a7cb8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table("company_payment_method_preferences",
    sa.Column("id", sa.UUID(), nullable=False),
    sa.Column("company_id", sa.UUID(), nullable=False),
    sa.Column("payment_method_id", sa.UUID(), nullable=False),
    sa.Column("available_at_pos", sa.Boolean(), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ),
    sa.ForeignKeyConstraint(["payment_method_id"], ["payment_method_catalog.id"], ),
    sa.PrimaryKeyConstraint("id"),
    sa.UniqueConstraint("company_id", "payment_method_id", name="uq_company_payment_method_pref")
    )
    op.create_index(op.f("ix_company_payment_method_preferences_company_id"), "company_payment_method_preferences", ["company_id"], unique=False)
    op.create_index(op.f("ix_company_payment_method_preferences_payment_method_id"), "company_payment_method_preferences", ["payment_method_id"], unique=False)

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.
    op.drop_column("payment_method_catalog", "available_at_pos")

    # ### data: backfill - for each existing company, default NU/CD/MB/TB to available at POS ###
    connection = op.get_bind()
    companies = connection.execute(sa.text("SELECT id FROM companies")).fetchall()
    default_codes = ["NU", "CD", "MB", "TB"]
    for (company_id,) in companies:
        for code in default_codes:
            method = connection.execute(
                sa.text("SELECT id FROM payment_method_catalog WHERE code = :code"),
                {"code": code},
            ).fetchone()
            if method is not None:
                connection.execute(
                    sa.text(
                        "INSERT INTO company_payment_method_preferences (id, company_id, payment_method_id, available_at_pos, created_at, updated_at) "
                        "VALUES (gen_random_uuid(), :company_id, :method_id, true, now(), now())"
                    ),
                    {"company_id": company_id, "method_id": method[0]},
                )


def downgrade() -> None:
    op.add_column("payment_method_catalog", sa.Column("available_at_pos", sa.BOOLEAN(), autoincrement=False, nullable=False, server_default=sa.text("false")))
    op.drop_index(op.f("ix_company_payment_method_preferences_payment_method_id"), table_name="company_payment_method_preferences")
    op.drop_index(op.f("ix_company_payment_method_preferences_company_id"), table_name="company_payment_method_preferences")
    op.drop_table("company_payment_method_preferences")
