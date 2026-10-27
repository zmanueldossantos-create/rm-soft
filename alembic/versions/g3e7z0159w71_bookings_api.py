"""bookings: updated_at, api_key_id, external_reference (bookings made through the public API)

Revision ID: g3e7z0159w71
Revises: f2d6y9048v60
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "g3e7z0159w71"
down_revision = "f2d6y9048v60"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("bookings", sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(),
                                        nullable=False))
    op.add_column("bookings", sa.Column("api_key_id", postgresql.UUID(as_uuid=True),
                                        sa.ForeignKey("api_keys.id", ondelete="SET NULL"), nullable=True))
    op.add_column("bookings", sa.Column("external_reference", sa.String(100), nullable=True))
    op.create_index("ix_bookings_external_reference", "bookings", ["external_reference"])


def downgrade() -> None:
    op.drop_index("ix_bookings_external_reference", table_name="bookings")
    op.drop_column("bookings", "external_reference")
    op.drop_column("bookings", "api_key_id")
    op.drop_column("bookings", "updated_at")
