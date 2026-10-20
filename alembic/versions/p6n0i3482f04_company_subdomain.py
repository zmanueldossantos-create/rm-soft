"""company subdomain (SaaS: one address per company)

Revision ID: p6n0i3482f04
Revises: o5m9h2371e93
"""
import re
import unicodedata

import sqlalchemy as sa
from alembic import op

revision = "p6n0i3482f04"
down_revision = "o5m9h2371e93"
branch_labels = None
depends_on = None

RESERVED = {"admin", "www", "api", "app", "mail", "static", "suporte", "support"}


def _slug(text: str) -> str:
    text = unicodedata.normalize("NFD", text or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:40].strip("-") or "empresa"


def upgrade() -> None:
    op.add_column("companies", sa.Column("subdomain", sa.String(63), nullable=True))
    op.create_index("ix_companies_subdomain", "companies", ["subdomain"], unique=True)
    # the existing companies get one from their short name (or name), made unique
    conn = op.get_bind()
    taken = set(RESERVED)
    for company_id, name, short_name in conn.execute(sa.text("SELECT id, name, short_name FROM companies ORDER BY created_at")):
        base = _slug(short_name or name)
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}-{n}", n + 1
        taken.add(candidate)
        conn.execute(sa.text("UPDATE companies SET subdomain = :s WHERE id = :i"), {"s": candidate, "i": company_id})


def downgrade() -> None:
    op.drop_index("ix_companies_subdomain", table_name="companies")
    op.drop_column("companies", "subdomain")
