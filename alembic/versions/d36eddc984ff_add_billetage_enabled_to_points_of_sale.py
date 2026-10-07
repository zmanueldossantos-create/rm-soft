"""add billetage_enabled to points_of_sale

Revision ID: d36eddc984ff
Revises: ee3855aeebb7
Create Date: 2026-09-08 10:19:11.831139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "d36eddc984ff"
down_revision: Union[str, None] = "ee3855aeebb7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default applies "false" to every existing row at add-time, so the
    # NOT NULL constraint never fails on the 2 POS already in the database.
    op.add_column(
        "points_of_sale",
        sa.Column("billetage_enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
    )

    # NOTE: 'uq_companies_name_lower' is a manually-created functional index
    # (lower(name)) not represented in the SQLAlchemy Company model, so
    # autogenerate flagged it as "removed" by mistake - intentionally NOT
    # touched here, same as in prior migrations.


def downgrade() -> None:
    op.drop_column("points_of_sale", "billetage_enabled")
