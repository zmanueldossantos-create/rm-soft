"""Apuramento do IVA (point 12, step 4): the VAT of a month - charged on sales, deductible on purchases, the result."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.vat_return_service import VatReturnError, get_vat_return, list_vat_documents, list_vat_periods

router = APIRouter(prefix="/api/v1/vat-return", tags=["vat-return"])


@router.get("/periods")
async def get_vat_periods(db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("vat:return"))):
    return await list_vat_periods(db, current_user.company_id)


@router.get("/{period_id}")
async def get_one_vat_return(period_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("vat:return"))):
    try:
        return await get_vat_return(db, current_user.company_id, period_id)
    except VatReturnError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{period_id}/documents")
async def get_vat_documents(period_id: uuid.UUID, side: str, tax_code: str, rate: float, exemption_code: str | None = None,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("vat:return"))):
    try:
        return await list_vat_documents(db, current_user.company_id, period_id, side, tax_code, rate, exemption_code)
    except VatReturnError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/{period_id}/pdf")
async def get_vat_return_pdf(period_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("vat:return"))):
    from app.services.cash_report_service import _company_dict
    from app.utils.vat_return_pdf import generate_vat_return_pdf
    try:
        data = await get_vat_return(db, current_user.company_id, period_id)
    except VatReturnError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    company = (await db.execute(select(Company).where(Company.id == current_user.company_id))).scalar_one()
    pdf = generate_vat_return_pdf(data, _company_dict(company))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="Apuramento-IVA-{data["period_label"].replace(" ", "-")}.pdf"'})
