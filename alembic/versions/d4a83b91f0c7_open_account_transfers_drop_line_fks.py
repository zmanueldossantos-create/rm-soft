"""open_account_transfers: line ids become plain references (no foreign key to open_account_lines)

Removing an item from an open account deletes its line (open_account_service.remove_line,
update_line_quantity down to 0). A foreign key from the audit table would block that with an
IntegrityError, while each audit row already carries every snapshot it needs (name, quantity,
price). Only constraints are dropped here - no data is touched.

Revision ID: d4a83b91f0c7
Revises: c91e5d7a2b36
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'd4a83b91f0c7'
down_revision: Union[str, None] = 'c91e5d7a2b36'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    for fk in inspector.get_foreign_keys('open_account_transfers'):
        if fk['constrained_columns'] in (['source_line_id'], ['target_line_id']) and fk.get('name'):
            op.drop_constraint(fk['name'], 'open_account_transfers', type_='foreignkey')


def downgrade() -> None:
    # Nothing to restore: the audit ids are plain references (see upgrade).
    pass
