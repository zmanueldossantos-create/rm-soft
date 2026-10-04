"""The article forms learn the exemption motive the company's regime imposes (or none)."""
import pytest

from app.models.fiscal_regime import FiscalRegime
from app.services.vat_rule_service import imposed_exemption


@pytest.mark.asyncio
async def test_the_motive_imposed_by_the_regime_is_given_to_the_forms(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, m11 = ctx["company"].id, ctx["exemption_m11"]
    regime = FiscalRegime(name="Regime teste imposto", allows_nor=False, allows_red=False, allows_ise=True,
                          required_exemption_id=m11.id)
    db.add(regime)
    await db.flush()
    ctx["company"].fiscal_regime_id = regime.id
    await db.commit()
    rule = await imposed_exemption(db, company_id)
    assert rule["regime"] == "Regime teste imposto"
    assert rule["exemption"] == {"id": str(m11.id), "code": "M11", "name": m11.name}
