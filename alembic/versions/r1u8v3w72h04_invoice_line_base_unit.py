"""invoice lines: a line sold in its base unit records that unit too (it was left empty, so the SAF-T wrote "UN" for
everything) - issued lines get the base unit of their product or service; the base unit is locked once an article has
history, so it is the unit they were sold in

Revision ID: r1u8v3w72h04
Revises: q0t7u2v61g93
"""
from alembic import op

revision = "r1u8v3w72h04"
down_revision = "q0t7u2v61g93"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE invoice_lines l SET unit_code_snapshot = u.code FROM products p JOIN unit_of_measure_catalog u "
        "ON u.id = p.unit_of_measure_id WHERE l.unit_code_snapshot IS NULL AND l.product_id = p.id"
    )
    op.execute(
        "UPDATE invoice_lines l SET unit_code_snapshot = u.code FROM services s JOIN unit_of_measure_catalog u "
        "ON u.id = s.unit_of_measure_id WHERE l.unit_code_snapshot IS NULL AND l.service_id = s.id"
    )


def downgrade() -> None:
    pass
