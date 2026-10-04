"""A company receives the legal VAT rates (catalog) of the categories its regime allows - all of them without a regime."""
from types import SimpleNamespace

import pytest

from app.models.legal_vat_rate import LegalVatRate
from app.services.company_service import _legal_rates_for


async def _seed(db):
    db.add_all([
        LegalVatRate(tax_category="ISE", name="Isento", rate=0),
        LegalVatRate(tax_category="RED", name="Taxa reduzida", rate=5),
        LegalVatRate(tax_category="NOR", name="Taxa normal", rate=14),
        LegalVatRate(tax_category="OUT", name="Outra", rate=2, is_active=False),
    ])
    await db.commit()


@pytest.mark.asyncio
async def test_a_regime_gets_the_active_legal_rates_it_allows(db):
    await _seed(db)
    simplified = SimpleNamespace(allows_nor=False, allows_red=False, allows_ise=True, allows_int=False, allows_out=True)
    assert [r.tax_category for r in await _legal_rates_for(db, simplified)] == ["ISE"]  # OUT allowed but inactive


@pytest.mark.asyncio
async def test_without_a_regime_every_active_legal_rate(db):
    await _seed(db)
    assert [r.tax_category for r in await _legal_rates_for(db, None)] == ["ISE", "RED", "NOR"]
