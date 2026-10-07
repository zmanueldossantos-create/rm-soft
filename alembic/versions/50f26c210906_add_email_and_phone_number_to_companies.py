"""Add email and phone_number to companies

Revision ID: 50f26c210906
Revises: cb8d03a6c0ec
Create Date: 2026-08-20 18:36:34.024516

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '50f26c210906'
down_revision: Union[str, None] = 'cb8d03a6c0ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('companies', sa.Column('email', sa.String(length=255), nullable=True))
    op.add_column('companies', sa.Column('phone_number', sa.String(length=20), nullable=True))

    # Backfill existing rows created before this migration (e.g. test data)
    op.execute("UPDATE companies SET email = 'sememail@rm-servicos.com' WHERE email IS NULL")
    op.execute("UPDATE companies SET phone_number = '+244900000000' WHERE phone_number IS NULL")

    op.alter_column('companies', 'email', nullable=False)
    op.alter_column('companies', 'phone_number', nullable=False)


def downgrade() -> None:
    op.drop_column('companies', 'phone_number')
    op.drop_column('companies', 'email')
