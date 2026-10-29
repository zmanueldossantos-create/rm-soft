"""Document series of the AGT: one per establishment and per N/C indicator (the unique key widened), the AGT's status
of the series and the contingência period; electronic series without an indicator become NORMAL.

Revision ID: l8j2c5604b26
Revises: k7i1b4593a15
"""
import sqlalchemy as sa
from alembic import op

revision = "l8j2c5604b26"
down_revision = "k7i1b4593a15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_series", sa.Column("agt_status", sa.String(1), nullable=True))
    op.add_column("document_series", sa.Column("series_start_ts", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document_series", sa.Column("series_end_ts", sa.DateTime(timezone=True), nullable=True))
    op.add_column("document_series", sa.Column("agt_synced_at", sa.DateTime(timezone=True), nullable=True))
    op.execute("UPDATE document_series SET contingency_indicator = 'NORMAL' "
               "WHERE issuance_mode = 'ELETRONICA' AND contingency_indicator IS NULL")
    op.drop_constraint("uq_series_company_doctype_year_mode", "document_series", type_="unique")
    op.execute("CREATE UNIQUE INDEX uq_series_scope ON document_series (company_id, document_type_id, year, "
               "issuance_mode, coalesce(establishment_id, '00000000-0000-0000-0000-000000000000'::uuid), "
               "coalesce(contingency_indicator, 'NORMAL'::contingencyindicator))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_series_scope")
    op.create_unique_constraint("uq_series_company_doctype_year_mode", "document_series",
                                ["company_id", "document_type_id", "year", "issuance_mode"])
    for column in ("agt_synced_at", "series_end_ts", "series_start_ts", "agt_status"):
        op.drop_column("document_series", column)
