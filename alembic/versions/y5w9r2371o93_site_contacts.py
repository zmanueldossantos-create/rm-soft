"""platform_settings.site_whatsapp / site_email: the contacts the public site shows (PUBLIC_SITE)

Revision ID: y5w9r2371o93
Revises: x4v8q1260n82
"""
import sqlalchemy as sa
from alembic import op

revision = "y5w9r2371o93"
down_revision = "x4v8q1260n82"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("site_whatsapp", sa.String(20), nullable=True))
    op.add_column("platform_settings", sa.Column("site_email", sa.String(120), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_settings", "site_email")
    op.drop_column("platform_settings", "site_whatsapp")
