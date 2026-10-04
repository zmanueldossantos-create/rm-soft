"""
VAT routes - READ-ONLY listing, scoped to the caller's company.
VAT rates are seeded automatically when a company is created (section 4.5 v6/v7).

DECISION (fiscal compliance, Priority #1 of the spec): VAT percentages are set by
Angolan law, not by individual businesses. GESTOR/ADMIN can view which rates apply
to their products, but cannot change the percentage values - a company changing
14% to 12% would break AGT compliance. Only a SUPER_ADMIN-level process (not yet
exposed via API) should ever adjust the legal rate values, if the law changes.
No update/create/delete route exists here on purpose.
"""
from pydantic import BaseModel as _BaseModel
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission, require_role
from app.models.user import User
from app.models.vat import VAT
from app.schemas.vat import VatResponse, VatRateCreateRequest, VatRateUpdateRequest
from app.services.vat_service import (
    list_company_vat_rates,
    create_company_vat_rate,
    update_company_vat_rate,
    toggle_company_vat_rate,
    VatRateNotFoundError,
    InvalidTaxCategoryError,
)

router = APIRouter(prefix="/api/v1/vat", tags=["vat"])


@router.get("", response_model=list[VatResponse])
async def get_vat_rates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("vat:view")),
):
    """Lists the active VAT rates for the caller's company (read-only)."""
    result = await db.execute(
        select(VAT).where(VAT.company_id == current_user.company_id, VAT.is_active == True).order_by(VAT.rate)
    )
    return result.scalars().all()



@router.get("/companies/{company_id}", response_model=list[VatResponse])
async def list_company_vat_rates_route(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """SUPER_ADMIN: lists ALL VAT rates (active and inactive) for a given company."""
    return await list_company_vat_rates(db, company_id)


@router.post("/companies/{company_id}", response_model=VatResponse, status_code=status.HTTP_201_CREATED)
async def create_company_vat_rate_route(
    company_id: uuid.UUID,
    payload: VatRateCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """SUPER_ADMIN: creates a new VAT rate for a given company - does not affect existing invoices/products."""
    try:
        return await create_company_vat_rate(db, company_id, payload.name, payload.rate, payload.tax_category)
    except VatRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidTaxCategoryError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/companies/{company_id}/{vat_id}", response_model=VatResponse)
async def update_company_vat_rate_route(
    company_id: uuid.UUID,
    vat_id: uuid.UUID,
    payload: VatRateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """SUPER_ADMIN: edits a company's VAT rate - already-issued invoices/products keep their own snapshot, unaffected."""
    try:
        return await update_company_vat_rate(db, company_id, vat_id, payload.name, payload.rate, payload.tax_category)
    except VatRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidTaxCategoryError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/companies/{company_id}/{vat_id}/toggle-status", response_model=VatResponse)
async def toggle_company_vat_rate_route(
    company_id: uuid.UUID,
    vat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """SUPER_ADMIN: activates/deactivates a company's VAT rate - deactivated rates stop appearing in the product/service dropdown."""
    try:
        return await toggle_company_vat_rate(db, company_id, vat_id)
    except VatRateNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


class ReclassifyRequest(_BaseModel):
    product_ids: list[uuid.UUID] = []
    service_ids: list[uuid.UUID] = []
    vat_id: uuid.UUID
    exemption_reason_id: uuid.UUID | None = None


@router.get("/reclassification")
async def get_articles_to_reclassify(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("vat:view")),
):
    """The products and services to reclassify after a regime change (they cannot be sold until then)."""
    from app.services.vat_rule_service import articles_to_reclassify
    return await articles_to_reclassify(db, current_user.company_id)


@router.post("/reclassify")
async def post_reclassify(
    payload: ReclassifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:manage")),
):
    """Gives several products and services one VAT rate (and motive), through THE article VAT rule."""
    from app.services.vat_rule_service import reclassify_articles
    count = await reclassify_articles(db, current_user.company_id, payload.product_ids, payload.service_ids,
                                      payload.vat_id, payload.exemption_reason_id)
    return {"reclassified": count}


@router.get("/article-rule")
async def get_article_vat_rule(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("vat:view")),
):
    """What the company's regime imposes on a sold article's VAT: the exemption motive of its exempt articles."""
    from app.services.vat_rule_service import imposed_exemption
    return await imposed_exemption(db, current_user.company_id)
