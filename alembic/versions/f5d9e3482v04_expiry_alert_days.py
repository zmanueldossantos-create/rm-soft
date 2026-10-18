"""expiry alert days

Lots et péremption: how many days before its expiry date a lot is "a expirar" (Stock > Validades), per company.

Revision ID: f5d9e3482v04
Revises: e4c8d2371u93
"""
import sqlalchemy as sa
from alembic import op

revision = "f5d9e3482v04"
down_revision = "e4c8d2371u93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("companies", sa.Column("expiry_alert_days", sa.Integer, nullable=False, server_default="30"))


def downgrade() -> None:
    op.drop_column("companies", "expiry_alert_days")
