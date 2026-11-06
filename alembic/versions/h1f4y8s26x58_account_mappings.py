"""Contabilidade - «Contas por operação» (the account of each kind of operation) and the sub-accounts the system makes
for each bank account, till, customer and supplier; whether customers / suppliers get one each.

Revision ID: h1f4y8s26x58
Revises: g0e3x7r15w47
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "h1f4y8s26x58"
down_revision = "g0e3x7r15w47"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounting_settings", sa.Column("subaccount_per_customer", sa.Boolean(), nullable=False, server_default="true"))
    op.add_column("accounting_settings", sa.Column("subaccount_per_supplier", sa.Boolean(), nullable=False, server_default="true"))
    op.create_table(
        "account_mappings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("operation", sa.String(40), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False),
        sa.UniqueConstraint("company_id", "operation", name="uq_account_mapping_operation"),
    )
    op.create_table(
        "account_links",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("company_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("companies.id"), nullable=False, index=True),
        sa.Column("entity_kind", sa.String(10), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("account_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("accounts.id"), nullable=False, index=True),
        sa.UniqueConstraint("company_id", "entity_kind", "entity_id", name="uq_account_link_entity"),
    )


def downgrade() -> None:
    op.drop_table("account_links")
    op.drop_table("account_mappings")
    op.drop_column("accounting_settings", "subaccount_per_supplier")
    op.drop_column("accounting_settings", "subaccount_per_customer")
