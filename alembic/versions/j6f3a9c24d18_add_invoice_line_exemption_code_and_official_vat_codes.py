"""add invoice_lines.exemption_code; complete the VAT exemption code catalog with the official codes

The SAF-T needs the exemption code (and its official reason) on every 0% line; like vat_rate_snapshot it is copied
onto the line when the document is issued. Additive only: one nullable column, the 16 official codes missing from
vat_codes (inserted only if absent, official reason as name) and the non-official "NA" made inactive so that it is
no longer offered (the super admin can reactivate it). No row is deleted and existing names are left untouched.

Revision ID: j6f3a9c24d18
Revises: i5e2d8b31c07
"""
import uuid
from datetime import date
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'j6f3a9c24d18'
down_revision: Union[str, None] = 'i5e2d8b31c07'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The 16 official codes absent from the catalog (frozen copy of the official texts).
NEW_CODES = [
    ("M10", "Isento nos termos da al\u00ednea a) do n\u00ba1 do artigo 12.\u00ba do CIVA"),
    ("M16", "Isento nos termos da al\u00ednea g) do n\u00ba1 do artigo 12.\u00ba do CIVA"),
    ("M37", "Isento nos termos da al\u00ednea h) do artigo 15.\u00ba do CIVA"),
    ("M38", "Isento nos termos da al\u00ednea i) do artigo 15.\u00ba do CIVA"),
    ("M80", "Isento nos termos da alinea a) do n\u00ba1 do artigo 14.\u00ba"),
    ("M81", "Isento nos termos da alinea b) do n\u00ba1 do artigo 14.\u00ba"),
    ("M82", "Isento nos termos da alinea c) do n\u00ba1 do artigo 14.\u00ba"),
    ("M83", "Isento nos termos da alinea d) do n\u00ba1 do artigo 14.\u00ba"),
    ("M84", "Isento nos termos da al\u00ednea e) do n\u00ba1 do artigo 14.\u00ba"),
    ("M85", "Isento nos termos da alinea a) do n\u00ba2 do artigo 14.\u00ba"),
    ("M86", "Isento nos termos da alinea b) do n\u00ba2 do artigo 14.\u00ba"),
    ("M90", "Isento nos termos da alinea a) do n\u00ba1 do artigo 16.\u00ba"),
    ("M91", "Isento nos termos da alinea b) do n\u00ba1 do artigo 16.\u00ba"),
    ("M92", "Isento nos termos da alinea c) do n\u00ba1 do artigo 16.\u00ba"),
    ("M93", "Isento nos termos da alinea d) do n\u00ba1 do artigo 16.\u00ba"),
    ("M94", "Isento nos termos da alinea e) do n\u00ba1 do artigo 16.\u00ba"),
]


def upgrade() -> None:
    bind = op.get_bind()
    existing = {c['name'] for c in sa.inspect(bind).get_columns('invoice_lines')}
    if 'exemption_code' not in existing:
        op.add_column('invoice_lines', sa.Column('exemption_code', sa.String(length=3), nullable=True))

    country_id = bind.execute(sa.text("SELECT country_id FROM vat_codes WHERE code = 'M04'")).scalar()
    if country_id is not None:
        for code, reason in NEW_CODES:
            if bind.execute(sa.text("SELECT 1 FROM vat_codes WHERE code = :code"), {"code": code}).first() is None:
                bind.execute(
                    sa.text(
                        "INSERT INTO vat_codes (id, code, name, rate, country_id, valid_from, valid_until, is_active) "
                        "VALUES (CAST(:id AS uuid), :code, :name, 0, :country, :valid_from, :valid_until, true)"
                    ),
                    {"id": str(uuid.uuid4()), "code": code, "name": reason, "country": country_id,
                     "valid_from": date(2021, 1, 1), "valid_until": date(9999, 12, 31)},
                )

    bind.execute(sa.text("UPDATE vat_codes SET is_active = false WHERE code = 'NA'"))


def downgrade() -> None:
    # Fiscal snapshot data and catalog rows are never dropped by a downgrade (the app never deletes data).
    raise RuntimeError("invoice_lines.exemption_code and the official VAT codes are never dropped by a downgrade")