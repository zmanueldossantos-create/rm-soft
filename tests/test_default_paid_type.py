"""The type used to close an open account / check out comes from the catalog: a type paid on issue."""
import pytest
from sqlalchemy import text

from app.services.document_rules import default_paid_on_issue_type


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_default_type_follows_the_catalog(db, company_with_essentials):
    assert await default_paid_on_issue_type(db) == "FACTURA_RECIBO"
    try:
        await _set_rule(db, "FR", paid_on_issue=False)
        await _set_rule(db, "FT", paid_on_issue=True)  # FT becomes the type paid on issue
        assert await default_paid_on_issue_type(db) == "FACTURA"
        await _set_rule(db, "FT", issuable_at_pos=False)  # none left: fall back to the Fatura/Recibo
        assert await default_paid_on_issue_type(db) == "FACTURA_RECIBO"
    finally:
        await _set_rule(db, "FR", paid_on_issue=True)
        await _set_rule(db, "FT", paid_on_issue=False, issuable_at_pos=True)