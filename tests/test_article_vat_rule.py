"""THE VAT rule of a sold article under its company's regime."""
import pytest

from app.models.fiscal_regime import FiscalRegime
from app.services.vat_rule_service import ArticleVatError, resolve_article_vat


async def _put_under(db, company, **regime_fields):
    regime = FiscalRegime(name="Regime teste " + str(len(regime_fields)) + str(sorted(regime_fields)), **regime_fields)
    db.add(regime)
    await db.flush()
    company.fiscal_regime_id = regime.id
    await db.commit()
    return regime


@pytest.mark.asyncio
async def test_a_rate_the_regime_does_not_allow_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    await _put_under(db, ctx["company"], allows_nor=True, allows_red=False, allows_ise=False)
    with pytest.raises(ArticleVatError, match="nao e permitida pelo regime"):
        await resolve_article_vat(db, ctx["company"].id, ctx["vat_red"].id, None)


@pytest.mark.asyncio
async def test_the_motive_imposed_by_the_regime_is_set_automatically(db, company_with_essentials):
    ctx = company_with_essentials
    m11 = ctx["exemption_m11"]
    await _put_under(db, ctx["company"], allows_nor=False, allows_red=False, allows_ise=True, required_exemption_id=m11.id)
    assert await resolve_article_vat(db, ctx["company"].id, ctx["vat_ise"].id, None) == m11.id


@pytest.mark.asyncio
async def test_a_taxed_article_carries_no_motive(db, company_with_essentials):
    ctx = company_with_essentials
    assert await resolve_article_vat(db, ctx["company"].id, ctx["vat_nor"].id, ctx["exemption_m11"].id) is None


@pytest.mark.asyncio
async def test_an_exempt_article_needs_a_motive(db, company_with_essentials):
    ctx = company_with_essentials
    with pytest.raises(ArticleVatError, match="obrigatorio"):
        await resolve_article_vat(db, ctx["company"].id, ctx["vat_ise"].id, None)
