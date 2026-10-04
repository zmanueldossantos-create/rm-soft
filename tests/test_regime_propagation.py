"""Editing a regime or a legal rate reaches at once the rates of the companies it concerns."""
import pytest
from sqlalchemy import select

from app.models.vat import VAT
from app.services.catalog_service import create_legal_vat_rate
from app.services.fiscal_regime_service import create_fiscal_regime, update_fiscal_regime


async def _active(db, company_id):
    rates = (await db.execute(select(VAT).where(VAT.company_id == company_id, VAT.is_active.is_(True)))).scalars().all()
    return sorted(r.tax_category for r in rates)


@pytest.mark.asyncio
async def test_editing_a_regime_resyncs_its_companies(db, company_with_essentials, legal_vat_rates):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    regime = await create_fiscal_regime(db, "Regime propagacao", None, True, False, False, False, False)
    regime_id = regime.id
    ctx["company"].fiscal_regime_id = regime_id
    await db.commit()

    await update_fiscal_regime(db, regime_id, "Regime propagacao", None, True, False, False, False, False)
    assert await _active(db, company_id) == ["NOR"]

    await update_fiscal_regime(db, regime_id, "Regime propagacao", None, True, True, False, False, False)  # RED ticked
    assert await _active(db, company_id) == ["NOR", "RED"]


@pytest.mark.asyncio
async def test_a_new_legal_rate_reaches_the_companies_whose_regime_allows_it(db, company_with_essentials, legal_vat_rates):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    regime = await create_fiscal_regime(db, "Regime com INT", None, True, False, False, True, False)
    ctx["company"].fiscal_regime_id = regime.id
    await db.commit()

    await create_legal_vat_rate(db, "INT", "Taxa intermedia", 7)
    intermediate = (await db.execute(
        select(VAT).where(VAT.company_id == company_id, VAT.tax_category == "INT")
    )).scalar_one()
    assert intermediate.is_active and float(intermediate.rate) == 7.0
