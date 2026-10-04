"""
THE VAT rule of a sold article (product or service) under its company's fiscal regime - one rule for both.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.fiscal_regime import FiscalRegime
from app.models.vat import VAT
from app.models.vat_code import VatCode


class ArticleVatError(Exception):
    """A VAT rate or exemption motive an article cannot carry under its company's regime."""


async def resolve_article_vat(
    db: AsyncSession, company_id: uuid.UUID, vat_id: uuid.UUID | None, exemption_reason_id: uuid.UUID | None,
) -> uuid.UUID | None:
    """
    Checks the VAT rate of a sold article and returns the exemption motive it must carry:
    - the rate belongs to the company and is active, and its category is allowed by the company's regime;
    - an exempt (ISE) article carries the motive its regime imposes (M00, M04 - set automatically), otherwise the
      motive chosen, which is required and must be active;
    - a taxed article (NOR, RED...) carries no motive.
    An article without a rate (a raw material, never sold) carries none either.
    """
    if vat_id is None:
        return None
    vat = (await db.execute(select(VAT).where(VAT.id == vat_id, VAT.company_id == company_id))).scalar_one_or_none()
    if vat is None or not vat.is_active:
        raise ArticleVatError("Taxa de IVA invalida ou inativa para esta empresa")
    regime = None
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    if company is not None and company.fiscal_regime_id is not None:
        regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one_or_none()
    if regime is not None and not getattr(regime, "allows_" + vat.tax_category.lower(), False):
        raise ArticleVatError(f"A taxa {vat.name} ({vat.tax_category}) nao e permitida pelo regime {regime.name} da empresa")
    if vat.tax_category != "ISE":
        return None
    if regime is not None and regime.required_exemption_id is not None:
        return regime.required_exemption_id
    if exemption_reason_id is None:
        raise ArticleVatError("Motivo de isencao obrigatorio para um artigo isento de IVA")
    motive = (await db.execute(
        select(VatCode).where(VatCode.id == exemption_reason_id, VatCode.is_active.is_(True))
    )).scalar_one_or_none()
    if motive is None:
        raise ArticleVatError("Motivo de isencao invalido ou inativo")
    return exemption_reason_id


async def imposed_exemption(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """
    What the company's regime imposes on its exempt articles, for the article forms: the regime's name and the
    exemption motive it imposes (id, code, legal mention) - None when each article chooses its own.
    """
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    regime = None
    if company is not None and company.fiscal_regime_id is not None:
        regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one_or_none()
    exemption = None
    if regime is not None and regime.required_exemption_id is not None:
        motive = (await db.execute(select(VatCode).where(VatCode.id == regime.required_exemption_id))).scalar_one_or_none()
        if motive is not None:
            exemption = {"id": str(motive.id), "code": motive.code, "name": motive.name}
    return {"regime": regime.name if regime is not None else None, "exemption": exemption}



# ---------- Reclassification after a regime change

async def _company_vat_context(db: AsyncSession, company_id: uuid.UUID):
    """The company's regime, its active rates (by id), the motive its regime imposes, and the motives other regimes
    impose (M00, M04... that become wrong once the company leaves those regimes)."""
    company = (await db.execute(select(Company).where(Company.id == company_id))).scalar_one_or_none()
    regime = None
    if company is not None and company.fiscal_regime_id is not None:
        regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id))).scalar_one_or_none()
    active_rates = {v.id: v for v in (await db.execute(
        select(VAT).where(VAT.company_id == company_id, VAT.is_active.is_(True))
    )).scalars().all()}
    imposed = regime.required_exemption_id if regime is not None else None
    others = {r for r in (await db.execute(
        select(FiscalRegime.required_exemption_id).where(FiscalRegime.required_exemption_id.is_not(None))
    )).scalars().all()} - {imposed}
    return regime, active_rates, imposed, others


def _needs_reclassification(article, active_rates: dict, others: set) -> bool:
    """THE test: a sold article whose rate is no longer active, or exempt with a motive another regime imposes."""
    if article.vat_id is None:
        return False  # a raw material, never sold
    vat = active_rates.get(article.vat_id)
    if vat is None:
        return True
    return vat.tax_category == "ISE" and article.exemption_reason_id in others


async def ensure_article_sellable(db: AsyncSession, article) -> None:
    """An article left behind by a regime change cannot be sold until it is reclassified."""
    _, active_rates, _, others = await _company_vat_context(db, article.company_id)
    if _needs_reclassification(article, active_rates, others):
        raise ArticleVatError(
            f"O artigo {article.name} tem de ser reclassificado (IVA) apos a mudanca de regime da empresa"
        )


async def articles_to_reclassify(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The products and services to reclassify after a regime change, for the banner and the grouped action."""
    from app.models.product import Product
    from app.models.service import Service
    _, active_rates, _, others = await _company_vat_context(db, company_id)
    result = {}
    for key, model in (("products", Product), ("services", Service)):
        rows = (await db.execute(select(model).where(model.company_id == company_id))).scalars().all()
        result[key] = [{"id": str(a.id), "code": a.code, "name": a.name} for a in rows
                       if _needs_reclassification(a, active_rates, others)]
    return result


async def auto_reclassify(db: AsyncSession, company_id: uuid.UUID, regime) -> None:
    """
    Under a regime that imposes a motive (Simplificado M00, Exclusao M04) there is no choice: every sold article takes
    the company's exempt (ISE) rate and that motive. Any other regime leaves the articles to the user. No commit.
    """
    if regime is None or regime.required_exemption_id is None:
        return
    from app.models.product import Product
    from app.models.service import Service
    exempt = (await db.execute(
        select(VAT).where(VAT.company_id == company_id, VAT.tax_category == "ISE", VAT.is_active.is_(True))
    )).scalars().first()
    if exempt is None:
        return
    for model in (Product, Service):
        for article in (await db.execute(
            select(model).where(model.company_id == company_id, model.vat_id.is_not(None))
        )).scalars().all():
            article.vat_id = exempt.id
            article.exemption_reason_id = regime.required_exemption_id


async def reclassify_articles(
    db: AsyncSession, company_id: uuid.UUID, product_ids: list, service_ids: list,
    vat_id: uuid.UUID, exemption_reason_id: uuid.UUID | None,
) -> int:
    """Gives several products and services one VAT rate (and motive), through THE article VAT rule. Returns the count."""
    from app.models.product import Product
    from app.models.service import Service
    motive = await resolve_article_vat(db, company_id, vat_id, exemption_reason_id)
    count = 0
    for model, ids in ((Product, product_ids), (Service, service_ids)):
        if not ids:
            continue
        for article in (await db.execute(
            select(model).where(model.company_id == company_id, model.id.in_(ids))
        )).scalars().all():
            article.vat_id = vat_id
            article.exemption_reason_id = motive
            count += 1
    await db.commit()
    return count
