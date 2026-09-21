"""A document type is only issued from the screens the catalog allows."""
import pytest
from fastapi import HTTPException
from sqlalchemy import text

from app.api.v1.issuable import ensure_issuable


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_ensure_issuable_follows_the_catalog(db, company_with_essentials):
    await ensure_issuable(db, "FACTURA", "invoices")
    await ensure_issuable(db, "FACTURA", "pos")
    await ensure_issuable(db, "PRO_FORMA", "invoices")
    with pytest.raises(HTTPException) as refused:
        await ensure_issuable(db, "NOTA_CREDITO", "invoices")  # a credit note is not issued from a screen of its own
    assert refused.value.status_code == 422
    with pytest.raises(HTTPException):
        await ensure_issuable(db, "ZQ0", "pos")  # unknown type

    try:
        await _set_rule(db, "FT", issuable_at_pos=False)
        with pytest.raises(HTTPException):
            await ensure_issuable(db, "FACTURA", "pos")
        await ensure_issuable(db, "FACTURA", "invoices")  # the other screen is unaffected
    finally:
        await _set_rule(db, "FT", issuable_at_pos=True)