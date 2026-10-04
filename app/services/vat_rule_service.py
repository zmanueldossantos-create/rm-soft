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
