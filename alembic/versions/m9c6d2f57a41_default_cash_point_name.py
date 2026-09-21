"""default cash points are all named "Caixa Geral" (the activity is shown next to the name where needed)

Data only: renames the default cash point of each activity (is_default) to "Caixa Geral", unless the activity already
has another cash point with that name. Nothing is deleted; the history keeps pointing at the same ids.

Revision ID: m9c6d2f57a41
Revises: l8b5c1e46f30
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'm9c6d2f57a41'
down_revision: Union[str, None] = 'l8b5c1e46f30'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

RENAME_SQL = """
UPDATE points_of_sale AS p
SET name = 'Caixa Geral'
WHERE p.is_default = true
  AND p.name <> 'Caixa Geral'
  AND NOT EXISTS (
      SELECT 1 FROM points_of_sale AS o
      WHERE o.activity_id = p.activity_id AND o.name = 'Caixa Geral' AND o.id <> p.id
  )
"""


def upgrade() -> None:
    op.get_bind().execute(sa.text(RENAME_SQL))


def downgrade() -> None:
    # Names are data: a downgrade never restores the old ones (the app never deletes data).
    raise RuntimeError('default cash point names are not restored by a downgrade')
