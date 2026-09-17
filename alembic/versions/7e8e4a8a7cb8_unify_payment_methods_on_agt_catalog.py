"""unify payment methods on AGT catalog

Revision ID: 7e8e4a8a7cb8
Revises: 97b8ac80d430
Create Date: 2026-09-10 14:24:23.654739

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "7e8e4a8a7cb8"
down_revision: Union[str, None] = "97b8ac80d430"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.

    # ### 1. New flags on payment_method_catalog ###
    op.add_column("payment_method_catalog", sa.Column("is_cash", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("payment_method_catalog", sa.Column("available_at_pos", sa.Boolean(), nullable=False, server_default=sa.text("false")))

    connection = op.get_bind()

    # ### 2. Null out any existing references to the old 9-code catalog before replacing it ###
    # (dev/test data only - see prior sessions' approach to base-data resets)
    connection.execute(sa.text("UPDATE customers SET payment_method_id = NULL WHERE payment_method_id IS NOT NULL"))
    connection.execute(sa.text("UPDATE invoices SET payment_method_id = NULL WHERE payment_method_id IS NOT NULL"))

    # ### 3. Replace the old 9-code catalog with the 12 official AGT PaymentMechanism codes ###
    connection.execute(sa.text("DELETE FROM payment_method_catalog"))
    agt_codes = [
        ("CC", "Cartao credito", False, False),
        ("CD", "Cartao debito", False, True),
        ("CH", "Cheque bancario", False, False),
        ("CI", "Credito documentario internacional", False, False),
        ("CO", "Cheque ou cartao oferta", False, False),
        ("CS", "Compensacao de saldos em conta corrente", False, False),
        ("DE", "Dinheiro electronico", False, False),
        ("MB", "Referencias de pagamento Multicaixa", False, True),
        ("NU", "Numerario", True, True),
        ("OU", "Outros meios de pagamento", False, False),
        ("PR", "Permuta de bens", False, False),
        ("TB", "Transferencia bancaria", False, True),
    ]
    for code, name, is_cash, available_at_pos in agt_codes:
        connection.execute(
            sa.text(
                "INSERT INTO payment_method_catalog (id, code, name, allows_payment, allows_receipt, is_cash, available_at_pos, is_active, created_at) "
                "VALUES (gen_random_uuid(), :code, :name, true, true, :is_cash, :available_at_pos, true, now())"
            ),
            {"code": code, "name": name, "is_cash": is_cash, "available_at_pos": available_at_pos},
        )

    # ### 4. payments.payment_method_id - added nullable first, backfilled, then locked NOT NULL ###
    op.add_column("payments", sa.Column("payment_method_id", sa.UUID(), nullable=True))

    # Map the old fixed enum values to their closest new AGT code, backfilling existing rows.
    old_to_new_code = {
        "NUMERARIO": "NU",
        "MULTICAIXA": "CD",
        "MULTICAIXA_EXPRESS": "MB",
        "TRANSFERENCIA": "TB",
        "OUTRO": "OU",
    }
    for old_value, new_code in old_to_new_code.items():
        connection.execute(
            sa.text(
                "UPDATE payments SET payment_method_id = "
                "(SELECT id FROM payment_method_catalog WHERE code = :new_code) "
                "WHERE payment_method = :old_value"
            ),
            {"new_code": new_code, "old_value": old_value},
        )

    op.alter_column("payments", "payment_method_id", existing_type=sa.UUID(), nullable=False)
    op.create_index(op.f("ix_payments_payment_method_id"), "payments", ["payment_method_id"], unique=False)
    op.create_foreign_key(None, "payments", "payment_method_catalog", ["payment_method_id"], ["id"])
    op.drop_column("payments", "payment_method")

    # Drop the now-unused server defaults (kept only to satisfy NOT NULL during backfill above)
    op.alter_column("payment_method_catalog", "is_cash", server_default=None)
    op.alter_column("payment_method_catalog", "available_at_pos", server_default=None)


def downgrade() -> None:
    op.add_column("payments", sa.Column("payment_method", postgresql.ENUM("NUMERARIO", "MULTICAIXA", "MULTICAIXA_EXPRESS", "TRANSFERENCIA", "OUTRO", name="paymentmethod"), autoincrement=False, nullable=True))
    op.drop_constraint(None, "payments", type_="foreignkey")
    op.drop_index(op.f("ix_payments_payment_method_id"), table_name="payments")
    op.drop_column("payments", "payment_method_id")
    op.drop_column("payment_method_catalog", "available_at_pos")
    op.drop_column("payment_method_catalog", "is_cash")
