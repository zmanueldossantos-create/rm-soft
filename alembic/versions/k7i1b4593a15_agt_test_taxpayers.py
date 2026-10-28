"""AGT test taxpayers (homologação): the AGT's test NIFs and their keys (platform-wide), and the test NIF a company
sends as while the environment is Homologação.

Revision ID: k7i1b4593a15
Revises: j6h0a3482z04
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "k7i1b4593a15"
down_revision = "j6h0a3482z04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "agt_test_taxpayers",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("nif", sa.String(20), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("private_key_encrypted", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.add_column("companies", sa.Column("agt_test_nif", sa.String(20), nullable=True))


def downgrade() -> None:
    op.drop_column("companies", "agt_test_nif")
    op.drop_table("agt_test_taxpayers")
