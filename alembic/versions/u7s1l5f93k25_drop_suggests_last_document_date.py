"""companies.suggests_last_document_date removed: the option «Sugere data do último documento» was never read by any
screen or service (a dead setting).

Revision ID: u7s1l5f93k25
Revises: t6r0k4e82j14
"""
import sqlalchemy as sa
from alembic import op

revision = "u7s1l5f93k25"
down_revision = "t6r0k4e82j14"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("companies", "suggests_last_document_date")


def downgrade() -> None:
    op.add_column("companies", sa.Column("suggests_last_document_date", sa.Boolean(), server_default="false", nullable=False))
