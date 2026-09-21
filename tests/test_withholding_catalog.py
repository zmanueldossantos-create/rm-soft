"""
The withholding catalog carries the SAF-T type (II, IPU...): the API only accepts the SAF-T codes, and updating a
withholding without sending a type keeps the one already set (the screen does not send it yet).
"""
import pytest
from pydantic import ValidationError

from app.schemas.catalog import WithholdingTaxRequest
from app.services.catalog_service import create_withholding_tax, update_withholding_tax


def test_request_accepts_only_saft_types():
    assert WithholdingTaxRequest(name="x", rate=1, tax_type="II").tax_type == "II"
    assert WithholdingTaxRequest(name="x").tax_type is None
    with pytest.raises(ValidationError):
        WithholdingTaxRequest(name="x", tax_type="IP")  # "IP" is the AGT API name, not the SAF-T code


@pytest.mark.asyncio
async def test_update_without_a_type_keeps_the_existing_one(db):
    item = await create_withholding_tax(db, "Teste tipo", 6.5, "II")
    item_id = item.id
    assert item.tax_type == "II"

    kept = await update_withholding_tax(db, item_id, "Teste tipo 2", 7.0)
    assert kept.tax_type == "II" and kept.name == "Teste tipo 2"

    changed = await update_withholding_tax(db, item_id, "Teste tipo 2", 7.0, "IPU")
    assert changed.tax_type == "IPU"