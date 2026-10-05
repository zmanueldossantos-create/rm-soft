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


class VatRateNotFoundError(Exception):
    pass


async def list_company_vat_rates(db: AsyncSession, company_id: uuid.UUID) -> list[VAT]:
    """Lists ALL VAT rates for a company (active and inactive) - for the SUPER_ADMIN
    management screen, unlike the GESTOR read-only route which only shows active ones."""
    result = await db.execute(select(VAT).where(VAT.company_id == company_id).order_by(VAT.rate))
    return list(result.scalars().all())


