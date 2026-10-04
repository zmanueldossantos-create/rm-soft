"""An exempt (ISE) article without a valid exemption motive is refused when the document is issued."""
from types import SimpleNamespace

import pytest

from app.services.invoice_service import MissingExemptionReasonError, _exemption_for


@pytest.mark.asyncio
async def test_an_exempt_article_without_a_motive_is_refused(db, company_with_essentials):
    ctx = company_with_essentials
    article = SimpleNamespace(name="Livro", company_id=ctx["company"].id, vat_id=ctx["vat_ise"].id, exemption_reason_id=None)
    with pytest.raises(MissingExemptionReasonError, match="Livro"):
        await _exemption_for(db, article, "ISE")


@pytest.mark.asyncio
async def test_a_taxed_article_needs_no_motive(db, company_with_essentials):
    ctx = company_with_essentials
    article = SimpleNamespace(name="Arroz", company_id=ctx["company"].id, vat_id=ctx["vat_nor"].id, exemption_reason_id=None)
    assert await _exemption_for(db, article, "NOR") == (None, None)
