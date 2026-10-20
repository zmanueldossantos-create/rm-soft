"""AI assistant on WhatsApp: the RM SOFT number's settings (WhatsApp Cloud API)

Revision ID: o5m9h2371e93
Revises: n4l8g1260d82
"""
import sqlalchemy as sa

from alembic import op

revision = "o5m9h2371e93"
down_revision = "n4l8g1260d82"
branch_labels = None
depends_on = None

COLUMNS = (
    ("whatsapp_phone_number_id", sa.String(40)), ("whatsapp_display_number", sa.String(20)),
    ("whatsapp_access_token_encrypted", sa.Text()), ("whatsapp_app_secret_encrypted", sa.Text()),
    ("whatsapp_verify_token", sa.String(64)),
)


def upgrade() -> None:
    for name, kind in COLUMNS:
        op.add_column("platform_settings", sa.Column(name, kind, nullable=True))


def downgrade() -> None:
    for name, _ in reversed(COLUMNS):
        op.drop_column("platform_settings", name)
