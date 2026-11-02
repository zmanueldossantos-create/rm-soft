"""services.activity_ids, product_categories.activity_ids: the activities whose tills offer the article (a Hotel
service only at the Receção, a Padaria category only at the counter). Empty = every activity, as before.

Revision ID: v8t2m6g04l36
Revises: u7s1l5f93k25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "v8t2m6g04l36"
down_revision = "u7s1l5f93k25"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("services", sa.Column("activity_ids", ARRAY(UUID(as_uuid=True)), nullable=True))
    op.add_column("product_categories", sa.Column("activity_ids", ARRAY(UUID(as_uuid=True)), nullable=True))


def downgrade() -> None:
    op.drop_column("product_categories", "activity_ids")
    op.drop_column("services", "activity_ids")
