"""A regime may impose an exemption motive (M00, M04...) - only if it allows exempt (ISE) rates."""
import pytest

from app.services.fiscal_regime_service import FiscalRegimeInvalidError, create_fiscal_regime


@pytest.mark.asyncio
async def test_a_regime_imposing_a_motive_must_allow_ise(db, company_with_essentials):
    motive = company_with_essentials["exemption_m11"]
    with pytest.raises(FiscalRegimeInvalidError, match="ISE"):
        await create_fiscal_regime(db, "Regime teste A", None, True, False, False, False, False, required_exemption_id=motive.id)


@pytest.mark.asyncio
async def test_a_regime_with_ise_keeps_its_imposed_motive(db, company_with_essentials):
    motive = company_with_essentials["exemption_m11"]
    regime = await create_fiscal_regime(db, "Regime teste B", None, False, False, True, False, False, required_exemption_id=motive.id)
    assert regime.required_exemption_id == motive.id
