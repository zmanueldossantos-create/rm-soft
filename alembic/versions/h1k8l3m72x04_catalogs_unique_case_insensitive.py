"""catalogs: no duplicates, whatever the case - unique indexes on lower(code / name), per company where the catalog is

Revision ID: h1k8l3m72x04
Revises: g0j7k2l61w93
"""
from alembic import op

revision = "h1k8l3m72x04"
down_revision = "g0j7k2l61w93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE UNIQUE INDEX uq_banks_acronym_ci ON banks (lower(acronym))")
    op.execute("CREATE UNIQUE INDEX uq_provinces_country_name_ci ON provinces (country_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_municipalities_province_name_ci ON municipalities (province_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_payment_terms_name_ci ON payment_terms (lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_product_categories_company_name_ci ON product_categories (company_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_vat_rates_company_name_ci ON vat_rates (company_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_withholding_taxes_name_ci ON withholding_taxes (lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_units_code_ci ON unit_of_measure_catalog (lower(code))")
    op.execute("CREATE UNIQUE INDEX uq_payment_methods_code_ci ON payment_method_catalog (lower(code))")
    op.execute("CREATE UNIQUE INDEX uq_vat_codes_code_ci ON vat_codes (lower(code))")
    op.execute("CREATE UNIQUE INDEX uq_movement_types_code_ci ON movement_types (lower(code))")
    op.execute("CREATE UNIQUE INDEX uq_countries_code_ci ON countries (lower(code))")
    op.execute("CREATE UNIQUE INDEX uq_fiscal_regimes_name_ci ON fiscal_regimes (lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_consumption_reasons_company_name_ci ON consumption_reason_catalog (company_id, lower(name))")
    op.execute("CREATE UNIQUE INDEX uq_resource_types_company_name_ci ON resource_type_catalog (company_id, lower(name))")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_banks_acronym_ci")
    op.execute("DROP INDEX IF EXISTS uq_provinces_country_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_municipalities_province_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_payment_terms_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_product_categories_company_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_vat_rates_company_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_withholding_taxes_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_units_code_ci")
    op.execute("DROP INDEX IF EXISTS uq_payment_methods_code_ci")
    op.execute("DROP INDEX IF EXISTS uq_vat_codes_code_ci")
    op.execute("DROP INDEX IF EXISTS uq_movement_types_code_ci")
    op.execute("DROP INDEX IF EXISTS uq_countries_code_ci")
    op.execute("DROP INDEX IF EXISTS uq_fiscal_regimes_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_consumption_reasons_company_name_ci")
    op.execute("DROP INDEX IF EXISTS uq_resource_types_company_name_ci")
