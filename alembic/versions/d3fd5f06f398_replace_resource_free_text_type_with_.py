"""replace resource free-text type with managed catalog

Revision ID: d3fd5f06f398
Revises: de9069751f47
Create Date: 2026-09-14 11:31:06.684232

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column


# revision identifiers, used by Alembic.
revision: str = 'd3fd5f06f398'
down_revision: Union[str, None] = 'de9069751f47'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table('resource_type_catalog',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('company_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=50), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('company_id', 'name', name='uq_resource_type_company_name')
    )
    op.create_index(op.f('ix_resource_type_catalog_company_id'), 'resource_type_catalog', ['company_id'], unique=False)
    # NOTE: 'uq_companies_name_lower' is a manually-created functional index (lower(name))
    # not represented in the SQLAlchemy Company model - intentionally NOT touched here.

    # Add the new column NULLABLE first - existing rows (e.g. "Quarto 101") have no
    # value yet, so a straight NOT NULL add would fail on any non-empty resources table.
    op.add_column('resources', sa.Column('resource_type_id', sa.UUID(), nullable=True))

    # Data migration: for every distinct (company_id, resource_type) pair still in use,
    # create one catalog entry (named after the old free-text value) and repoint every
    # matching resource row at it - preserves existing data (e.g. "Quarto 101" / "CHAMBRE")
    # instead of losing it.
    bind = op.get_bind()
    distinct_pairs = bind.execute(sa.text("SELECT DISTINCT company_id, resource_type FROM resources")).fetchall()
    for company_id, resource_type in distinct_pairs:
        new_id = uuid.uuid4()
        bind.execute(
            sa.text("INSERT INTO resource_type_catalog (id, company_id, name, is_active) VALUES (:id, :company_id, :name, true)"),
            {"id": new_id, "company_id": company_id, "name": resource_type},
        )
        bind.execute(
            sa.text("UPDATE resources SET resource_type_id = :new_id WHERE company_id = :company_id AND resource_type = :resource_type"),
            {"new_id": new_id, "company_id": company_id, "resource_type": resource_type},
        )

    op.alter_column('resources', 'resource_type_id', nullable=False)
    op.create_index(op.f('ix_resources_resource_type_id'), 'resources', ['resource_type_id'], unique=False)
    op.create_foreign_key(None, 'resources', 'resource_type_catalog', ['resource_type_id'], ['id'])
    op.drop_column('resources', 'resource_type')


def downgrade() -> None:
    op.add_column('resources', sa.Column('resource_type', sa.VARCHAR(length=30), autoincrement=False, nullable=True))
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE resources SET resource_type = rtc.name
        FROM resource_type_catalog rtc
        WHERE resources.resource_type_id = rtc.id
    """))
    op.alter_column('resources', 'resource_type', nullable=False)
    op.drop_constraint(None, 'resources', type_='foreignkey')
    op.drop_index(op.f('ix_resources_resource_type_id'), table_name='resources')
    op.drop_column('resources', 'resource_type_id')
    op.drop_index(op.f('ix_resource_type_catalog_company_id'), table_name='resource_type_catalog')
    op.drop_table('resource_type_catalog')
