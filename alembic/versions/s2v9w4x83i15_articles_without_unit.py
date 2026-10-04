"""products and services without a base unit get the catalog unit UN (a service is billed by the unit unless the GESTOR
sets another), and their invoice lines get it too - the SAF-T needs a unit on every line

Revision ID: s2v9w4x83i15
Revises: r1u8v3w72h04
"""
from alembic import op

revision = "s2v9w4x83i15"
down_revision = "r1u8v3w72h04"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE products SET unit_of_measure_id = (SELECT id FROM unit_of_measure_catalog WHERE code = 'UN') "
               "WHERE unit_of_measure_id IS NULL")
    op.execute("UPDATE services SET unit_of_measure_id = (SELECT id FROM unit_of_measure_catalog WHERE code = 'UN') "
               "WHERE unit_of_measure_id IS NULL")
    op.execute(
        "UPDATE invoice_lines l SET unit_code_snapshot = u.code FROM services s JOIN unit_of_measure_catalog u "
        "ON u.id = s.unit_of_measure_id WHERE l.unit_code_snapshot IS NULL AND l.service_id = s.id"
    )
    op.execute(
        "UPDATE invoice_lines l SET unit_code_snapshot = u.code FROM products p JOIN unit_of_measure_catalog u "
        "ON u.id = p.unit_of_measure_id WHERE l.unit_code_snapshot IS NULL AND l.product_id = p.id"
    )


def downgrade() -> None:
    pass
