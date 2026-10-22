"""plans and company_contracts (Planos): the 4 starting plans, and every existing company on Empresarial with no end

Revision ID: v2t6o9048l60
Revises: u1s5n8937k59
"""
import os
import uuid
from datetime import date

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "v2t6o9048l60"
down_revision = "u1s5n8937k59"
branch_labels = None
depends_on = None

# The starting plans - only a starting point: the SUPER_ADMIN changes everything in «Planos».
# limits: null = unlimited. Prices in Kz: monthly, quarterly, semiannual, annual, lifetime.
PLANS = [
    ("Essencial", "Para começar: um negócio, uma caixa", (6500, 18500, 35000, 65000, 195000),
     {"max_users": 3, "max_modules": 1, "max_establishments": 1, "max_pos": 1, "max_warehouses": 1},
     [], False, 1),
    ("Profissional", "Stock completo, fornecedores e guias, até dois negócios", (12500, 36000, 69000, 125000, 375000),
     {"max_users": 10, "max_modules": 2, "max_establishments": 2, "max_pos": 3, "max_warehouses": 3},
     ["FORNECEDORES_COMPRAS", "GUIAS", "APURAMENTO_IVA", "COPIAS_AUTOMATICAS"], True, 2),
    ("Empresarial", "Vários negócios sob o mesmo NIF, com o assistente IA", (20000, 57000, 110000, 200000, 600000),
     {"max_users": 25, "max_modules": 4, "max_establishments": 5, "max_pos": 10, "max_warehouses": None},
     ["FORNECEDORES_COMPRAS", "GUIAS", "APURAMENTO_IVA", "COPIAS_AUTOMATICAS", "PERMISSOES_PERSONALIZADAS",
      "ASSISTENTE_IA"], False, 3),
    ("Personalizado", "Sob cotação: sem limites, instalação e formação à medida", (None, None, None, None, None),
     {"max_users": None, "max_modules": None, "max_establishments": None, "max_pos": None, "max_warehouses": None},
     ["FORNECEDORES_COMPRAS", "GUIAS", "APURAMENTO_IVA", "COPIAS_AUTOMATICAS", "PERMISSOES_PERSONALIZADAS",
      "ASSISTENTE_IA", "IA_CANAIS"], False, 4),
]


def upgrade() -> None:
    plans = op.create_table(
        "plans",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(60), nullable=False, unique=True),
        sa.Column("description", sa.String(300), nullable=True),
        sa.Column("price_monthly", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_quarterly", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_semiannual", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_annual", sa.Numeric(14, 2), nullable=True),
        sa.Column("price_lifetime", sa.Numeric(14, 2), nullable=True),
        sa.Column("maintenance_percent", sa.Numeric(5, 2), nullable=True),
        sa.Column("limits", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("options", postgresql.ARRAY(sa.String(40)), nullable=False, server_default="{}"),
        sa.Column("is_popular", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_table(
        "company_contracts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False),
        sa.Column("plan_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("plans.id"), nullable=False),
        sa.Column("deployment_mode", sa.String(10), nullable=False),
        sa.Column("billing", sa.String(12), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=True),
        sa.Column("maintenance_until", sa.Date(), nullable=True),
        sa.Column("addons", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column("is_current", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_company_contracts_company_id", "company_contracts", ["company_id"])
    op.create_index("uq_company_contract_current", "company_contracts", ["company_id"], unique=True,
                    postgresql_where=sa.text("is_current"))

    rows, empresarial = [], None
    for name, description, prices, limits, options, popular, order in PLANS:
        plan_id = uuid.uuid4()
        if name == "Empresarial":
            empresarial = plan_id
        monthly, quarterly, semiannual, annual, lifetime = prices
        rows.append({"id": plan_id, "name": name, "description": description, "price_monthly": monthly,
                     "price_quarterly": quarterly, "price_semiannual": semiannual, "price_annual": annual,
                     "price_lifetime": lifetime, "maintenance_percent": 20 if lifetime else None, "limits": limits,
                     "options": options, "is_popular": popular, "sort_order": order, "is_active": True})
    op.bulk_insert(plans, rows)

    # the companies of before the plans: Empresarial, no end date - nobody is blocked; changed in «Contrato»
    mode = "SAAS" if os.getenv("DEPLOYMENT_MODE", "local").lower() == "saas" else "LOCAL"
    op.get_bind().execute(sa.text(
        "INSERT INTO company_contracts (id, company_id, plan_id, deployment_mode, billing, start_date, end_date, "
        "addons, notes, is_current) SELECT gen_random_uuid(), id, :plan, :mode, 'ANUAL', :today, NULL, '{}'::jsonb, "
        "'Empresa anterior aos planos', true FROM companies"
    ), {"plan": empresarial, "mode": mode, "today": date.today()})


def downgrade() -> None:
    op.drop_index("uq_company_contract_current", table_name="company_contracts")
    op.drop_index("ix_company_contracts_company_id", table_name="company_contracts")
    op.drop_table("company_contracts")
    op.drop_table("plans")
