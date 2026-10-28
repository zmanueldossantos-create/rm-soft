"""AGT (Faturação Eletrónica): the producer's access and the software's signature on platform_settings, the taxpayer's
key (encrypted) on companies - companies.electronic_signature_key (kept in clear, shown on screens) is dropped;
agt_calls: the journal of the calls to the AGT.

Revision ID: j6h0a3482z04
Revises: i5g9b2371y93
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "j6h0a3482z04"
down_revision = "i5g9b2371y93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_settings", sa.Column("agt_environment", sa.String(20), nullable=False,
                                                 server_default="HOMOLOGACAO"))
    op.add_column("platform_settings", sa.Column("agt_username", sa.String(100), nullable=True))
    op.add_column("platform_settings", sa.Column("agt_password_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column("agt_product_id", sa.String(100), nullable=True))
    op.add_column("platform_settings", sa.Column("agt_signature_version", sa.Integer(), nullable=True))
    op.add_column("platform_settings", sa.Column("agt_software_key_encrypted", sa.Text(), nullable=True))
    op.add_column("platform_settings", sa.Column("agt_software_signature", sa.Text(), nullable=True))
    op.add_column("companies", sa.Column("agt_private_key_encrypted", sa.Text(), nullable=True))
    op.drop_column("companies", "electronic_signature_key")
    op.create_table(
        "agt_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id", ondelete="CASCADE"),
                  nullable=True),
        sa.Column("service", sa.String(40), nullable=False),
        sa.Column("environment", sa.String(20), nullable=False),
        sa.Column("request_body", postgresql.JSONB(), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", postgresql.JSONB(), nullable=True),
        sa.Column("error", sa.String(300), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_agt_calls_company_created", "agt_calls", ["company_id", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_agt_calls_company_created", table_name="agt_calls")
    op.drop_table("agt_calls")
    op.add_column("companies", sa.Column("electronic_signature_key", sa.String(1000), nullable=True))
    op.drop_column("companies", "agt_private_key_encrypted")
    for column in ("agt_software_signature", "agt_software_key_encrypted", "agt_signature_version", "agt_product_id",
                   "agt_password_encrypted", "agt_username", "agt_environment"):
        op.drop_column("platform_settings", column)
