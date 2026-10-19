"""pharmacy: medicines, pharmaceutical forms, exemptions kept by a regime

- products: is_medicine, active substance (DCI), pharmaceutical form, dosage, dispensing regime, cold storage;
- pharmaceutical_forms: the GESTOR's managed list of dosage forms;
- fiscal_regimes.kept_exemption_ids: the exemptions that still apply under a regime imposing a motive;
- the Farmácia module (already seeded with Stock only) also gives the new Farmácia capability.

Revision ID: h7f2a5604x26
Revises: g6e1f4593w15
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import ARRAY, UUID

revision = "h7f2a5604x26"
down_revision = "g6e1f4593w15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pharmaceutical_forms",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("uq_pharmaceutical_forms_company_name_ci", "pharmaceutical_forms",
                    ["company_id", sa.text("lower(name)")], unique=True)

    op.add_column("products", sa.Column("is_medicine", sa.Boolean, nullable=False, server_default="false"))
    op.add_column("products", sa.Column("active_substance", sa.String(150), nullable=True))
    op.add_column("products", sa.Column("pharmaceutical_form_id", UUID(as_uuid=True),
                                        sa.ForeignKey("pharmaceutical_forms.id"), nullable=True))
    op.add_column("products", sa.Column("dosage", sa.String(60), nullable=True))
    op.add_column("products", sa.Column("dispensing_regime", sa.String(20), nullable=True))
    op.add_column("products", sa.Column("cold_storage", sa.Boolean, nullable=False, server_default="false"))

    op.add_column("fiscal_regimes", sa.Column("kept_exemption_ids", ARRAY(UUID(as_uuid=True)), nullable=False,
                                              server_default="{}"))

    # The Farmácia module was seeded while in development (Stock only): it now gives the Farmácia capability too.
    op.execute("""
        INSERT INTO module_capabilities (module_id, capability, is_enabled)
        SELECT id, 'PHARMACY', true FROM modules WHERE code = 'FARMACIA'
        ON CONFLICT (module_id, capability) DO UPDATE SET is_enabled = true
    """)


def downgrade() -> None:
    op.execute("DELETE FROM module_capabilities WHERE capability = 'PHARMACY'")
    op.drop_column("fiscal_regimes", "kept_exemption_ids")
    op.drop_column("products", "cold_storage")
    op.drop_column("products", "dispensing_regime")
    op.drop_column("products", "dosage")
    op.drop_column("products", "pharmaceutical_form_id")
    op.drop_column("products", "active_substance")
    op.drop_column("products", "is_medicine")
    op.drop_index("uq_pharmaceutical_forms_company_name_ci", table_name="pharmaceutical_forms")
    op.drop_table("pharmaceutical_forms")
