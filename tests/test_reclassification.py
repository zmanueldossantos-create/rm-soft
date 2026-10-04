"""After a regime change: a regime that imposes a motive reclassifies the articles at once; leaving it leaves them to
reclassify - refused at sale until then - and a grouped reclassification makes them sellable again."""
import pytest
from sqlalchemy import select

from app.models.fiscal_regime import FiscalRegime
from app.models.product import Product, ProductType
from app.services.company_service import sync_company_rates
from app.services.vat_rule_service import (
    ArticleVatError, articles_to_reclassify, ensure_article_sellable, reclassify_articles,
)


async def _setup(db, ctx):
    imposing = FiscalRegime(name="Exclusao (reclass)", allows_nor=False, allows_red=False, allows_ise=True,
                            required_exemption_id=ctx["exemption_m11"].id)
    general = FiscalRegime(name="Geral (reclass)", allows_nor=True, allows_red=True, allows_ise=True)
    product = Product(company_id=ctx["company"].id, code="RC-1", name="Artigo reclass", vat_id=ctx["vat_nor"].id,
                      price=100.0, min_stock_threshold=0, product_type=ProductType.BEM)
    db.add_all([imposing, general, product])
    await db.commit()
    return imposing, general, product.id


async def _move(db, ctx, regime):
    ctx["company"].fiscal_regime_id = regime.id
    await sync_company_rates(db, ctx["company"].id, regime)
    await db.commit()


@pytest.mark.asyncio
async def test_a_regime_imposing_a_motive_reclassifies_the_articles_at_once(db, company_with_essentials, legal_vat_rates):
    ctx = company_with_essentials
    imposing, _, product_id = await _setup(db, ctx)
    await _move(db, ctx, imposing)
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    assert product.vat_id == ctx["vat_ise"].id and product.exemption_reason_id == ctx["exemption_m11"].id


@pytest.mark.asyncio
async def test_leaving_it_leaves_the_articles_to_reclassify_and_unsellable(db, company_with_essentials, legal_vat_rates):
    ctx = company_with_essentials
    imposing, general, product_id = await _setup(db, ctx)
    await _move(db, ctx, imposing)
    await _move(db, ctx, general)
    pending = await articles_to_reclassify(db, ctx["company"].id)
    assert [p["code"] for p in pending["products"]] == ["RC-1"]
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    with pytest.raises(ArticleVatError, match="reclassificado"):
        await ensure_article_sellable(db, product)


@pytest.mark.asyncio
async def test_a_grouped_reclassification_makes_them_sellable(db, company_with_essentials, legal_vat_rates):
    ctx = company_with_essentials
    imposing, general, product_id = await _setup(db, ctx)
    await _move(db, ctx, imposing)
    await _move(db, ctx, general)
    count = await reclassify_articles(db, ctx["company"].id, [product_id], [], ctx["vat_nor"].id, None)
    assert count == 1
    assert (await articles_to_reclassify(db, ctx["company"].id))["products"] == []
    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one()
    await ensure_article_sellable(db, product)
