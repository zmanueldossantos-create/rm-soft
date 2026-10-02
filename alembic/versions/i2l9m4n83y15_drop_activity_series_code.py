"""activities: series_code dropped - generated, checked for uniqueness, never read (numbering goes through document_series)

Revision ID: i2l9m4n83y15
Revises: h1k8l3m72x04
"""
from alembic import op
import sqlalchemy as sa

revision = "i2l9m4n83y15"
down_revision = "h1k8l3m72x04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("uq_activity_company_series_code", "activities", type_="unique")
    op.drop_column("activities", "series_code")


def downgrade() -> None:
    op.add_column("activities", sa.Column("series_code", sa.String(10), nullable=True))
