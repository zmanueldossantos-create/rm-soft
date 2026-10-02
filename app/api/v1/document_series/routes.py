"""
DocumentSeries routes - scoped to the caller's company (Video 4/8).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.company import Company
from app.schemas.document_series import DocumentSeriesCreateRequest, DocumentSeriesUpdateRequest, DocumentSeriesResponse
from app.services.document_series_service import (
    list_series,
    create_series,
    update_series,
    toggle_series,
    SeriesAlreadyExistsError,
    ManualSeriesCodeRequiredError,
    SeriesNotFoundError,
    ElectronicTypeNotEligibleError,
    TodosNotAllowedInElectronicError,
)

router = APIRouter(prefix="/api/v1/document-series", tags=["document-series"])


@router.get("", response_model=list[DocumentSeriesResponse])
async def get_series(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document_series:view")),
):
    return await list_series(db, current_user.company_id)


@router.post("", response_model=list[DocumentSeriesResponse], status_code=status.HTTP_201_CREATED)
async def post_series(
    payload: DocumentSeriesCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document_series:manage")),
):
    """Returns a list: usually one series, or several when document_type_id is omitted ("Todos")."""
    company_result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = company_result.scalar_one()
    try:
        return await create_series(
            db, company,
            document_type_id=payload.document_type_id,
            year=payload.year,
            establishment_id=payload.establishment_id,
            series_code=payload.series_code,
            description=payload.description,
            contingency_indicator=payload.contingency_indicator,
            is_predefined=payload.is_predefined,
            todos_facturacao=payload.todos_facturacao,
            todos_tesouraria=payload.todos_tesouraria,
            todos_compras=payload.todos_compras,
        )
    except SeriesAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ManualSeriesCodeRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ElectronicTypeNotEligibleError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except TodosNotAllowedInElectronicError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{series_id}/toggle-status", response_model=DocumentSeriesResponse)
async def toggle_series_status(
    series_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document_series:manage")),
):
    try:
        return await toggle_series(db, current_user.company_id, series_id)
    except SeriesNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{series_id}", response_model=DocumentSeriesResponse)
async def patch_series(
    series_id: uuid.UUID,
    payload: DocumentSeriesUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("document_series:manage")),
):
    try:
        return await update_series(db, current_user.company_id, series_id, payload.description, payload.contingency_indicator, payload.is_predefined)
    except SeriesNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))



@router.get("/allowed-years")
async def get_allowed_series_years(
    current_user: User = Depends(require_permission("document_series:manage")),
):
    """The years a series can be created for (the AGT rule: the next year too after 15 December)."""
    from app.services.document_series_service import allowed_series_years
    return {"years": allowed_series_years()}
