"""Marca do software: platform_settings.brand_name, brand_logo_path, brand_header (NOME | LOGO), brand_show_vendor -
the name and logo the users of an installation see (a client may have the software under its own name).

Revision ID: t6r0k4e82j14
Revises: s5q9j3d71i03
"""
import sqlalchemy as sa
from alembic import op

revision = "t6r0k4e82j14"
down_revision = "s5q9j3d71i03"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("brand_name", sa.String(60), nullable=True))
    op.add_column("platform_settings", sa.Column("brand_logo_path", sa.String(200), nullable=True))
    op.add_column("platform_settings", sa.Column("brand_header", sa.String(10), server_default="NOME", nullable=False))
    op.add_column("platform_settings", sa.Column("brand_show_vendor", sa.Boolean(), server_default="true", nullable=False))


def downgrade() -> None:
    op.drop_column("platform_settings", "brand_show_vendor")
    op.drop_column("platform_settings", "brand_header")
    op.drop_column("platform_settings", "brand_logo_path")
    op.drop_column("platform_settings", "brand_name")
