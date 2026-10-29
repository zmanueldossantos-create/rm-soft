"""Faturação Eletrónica: the address of the QR code printed on an electronic document, set by the SUPER_ADMIN
(platform_settings.agt_qr_url, None = the default of app.services.agt_document_service).

Revision ID: p2n6g0a48f70
Revises: o1m5f8937e59
"""
import sqlalchemy as sa
from alembic import op

revision = "p2n6g0a48f70"
down_revision = "o1m5f8937e59"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("agt_qr_url", sa.String(300), nullable=True))


def downgrade() -> None:
    op.drop_column("platform_settings", "agt_qr_url")
