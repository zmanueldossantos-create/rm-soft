"""
VAT management service - SUPER_ADMIN only (see app/api/v1/vat/routes.py for the
read-only GESTOR listing, which explicitly left this unbuilt: "Only a SUPER_ADMIN-level
process should ever adjust the legal rate values").

VAT rows are scoped to a single company (VAT.company_id) - a SUPER_ADMIN targets a
specific company explicitly rather than editing a platform-wide catalog. Changing or
deactivating a rate NEVER touches already-issued invoices or existing product/service
vat_id assignments (those keep referencing the row as it was at the time), so historical
documents remain accurate even if the company's regime later changes.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vat import VAT
from app.models.company import Company


VALID_TAX_CATEGORIES = ("NOR", "RED", "ISE", "INT", "OUT")


class VatRateNotFoundError(Exception):
    pass


class InvalidTaxCategoryError(Exception):
    pass


def _validate_category(tax_category: str) -> None:
    if tax_category not in VALID_TAX_CATEGORIES:
        raise InvalidTaxCategoryError(
            f"Categoria de imposto invalida - deve ser uma de: {', '.join(VALID_TAX_CATEGORIES)}"
        )


async def list_company_vat_rates(db: AsyncSession, company_id: uuid.UUID) -> list[VAT]:
    """Lists ALL VAT rates for a company (active and inactive) - for the SUPER_ADMIN
    management screen, unlike the GESTOR read-only route which only shows active ones."""
    result = await db.execute(select(VAT).where(VAT.company_id == company_id).order_by(VAT.rate))
    return list(result.scalars().all())


async def create_company_vat_rate(
    db: AsyncSession, company_id: uuid.UUID, name: str, rate: float, tax_category: str,
) -> VAT:
    company_result = await db.execute(select(Company).where(Company.id == company_id))
    if company_result.scalar_one_or_none() is None:
        raise VatRateNotFoundError("Empresa nao encontrada")

    _validate_category(tax_category)

    vat = VAT(company_id=company_id, name=name, rate=rate, tax_category=tax_category, is_active=True)
    db.add(vat)
    await db.commit()
    await db.refresh(vat)
    return vat


async def update_company_vat_rate(
    db: AsyncSession, company_id: uuid.UUID, vat_id: uuid.UUID, name: str, rate: float, tax_category: str,
) -> VAT:
    result = await db.execute(select(VAT).where(VAT.id == vat_id, VAT.company_id == company_id))
    vat = result.scalar_one_or_none()
    if vat is None:
        raise VatRateNotFoundError("Taxa de IVA nao encontrada")

    _validate_category(tax_category)

    vat.name = name
    vat.rate = rate
    vat.tax_category = tax_category
    await db.commit()
    await db.refresh(vat)
    return vat


async def toggle_company_vat_rate(db: AsyncSession, company_id: uuid.UUID, vat_id: uuid.UUID) -> VAT:
    result = await db.execute(select(VAT).where(VAT.id == vat_id, VAT.company_id == company_id))
    vat = result.scalar_one_or_none()
    if vat is None:
        raise VatRateNotFoundError("Taxa de IVA nao encontrada")

    vat.is_active = not vat.is_active
    await db.commit()
    await db.refresh(vat)
    return vat
