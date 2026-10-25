"""demo_requests (the public site's «Pedir demonstração») and plans.description_en (the site in English)

Revision ID: a7y1t4593q15
Revises: y5w9r2371o93
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "a7y1t4593q15"
down_revision = "y5w9r2371o93"
branch_labels = None
depends_on = None


# the English descriptions of the 4 starting plans (v2t6o9048l60), for the public site - edited later in «Planos»
DESCRIPTIONS_EN = {
    "Essencial": "To start: one business, one till",
    "Profissional": "Full stock, suppliers and delivery notes, up to two businesses",
    "Empresarial": "Several businesses under one NIF, with the AI assistant",
    "Personalizado": "On quotation: no limits, installation and training made to measure",
}


def upgrade() -> None:
    op.add_column("plans", sa.Column("description_en", sa.String(300), nullable=True))
    for name, text in DESCRIPTIONS_EN.items():
        op.get_bind().execute(sa.text("UPDATE plans SET description_en = :text WHERE name = :name AND description_en IS NULL"),
                              {"text": text, "name": name})
    op.create_table(
        "demo_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("company_name", sa.String(160), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("email", sa.String(160), nullable=True),
        sa.Column("nif", sa.String(20), nullable=True),
        sa.Column("sectors", postgresql.ARRAY(sa.String(30)), nullable=False, server_default="{}"),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id", ondelete="SET NULL"), nullable=True),
        sa.Column("deployment", sa.String(10), nullable=False, server_default="NAO_SEI"),
        sa.Column("message", sa.String(1000), nullable=True),
        sa.Column("language", sa.String(2), nullable=False, server_default="pt"),
        sa.Column("ip", sa.String(45), nullable=True),
        sa.Column("status", sa.String(12), nullable=False, server_default="NOVO"),
        sa.Column("notes", sa.String(2000), nullable=True),
        sa.Column("handled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_demo_requests_status", "demo_requests", ["status"])
    op.create_index("ix_demo_requests_created_at", "demo_requests", ["created_at"])
    op.create_index("ix_demo_requests_ip_created", "demo_requests", ["ip", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_demo_requests_ip_created", table_name="demo_requests")
    op.drop_index("ix_demo_requests_created_at", table_name="demo_requests")
    op.drop_index("ix_demo_requests_status", table_name="demo_requests")
    op.drop_table("demo_requests")
    op.drop_column("plans", "description_en")
