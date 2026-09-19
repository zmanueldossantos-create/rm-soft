"""
Establishment routes - scoped to the caller's company (Video 8).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.establishment import EstablishmentRequest, EstablishmentResponse
from app.services.establishment_service import (
    list_establishments,
    create_establishment,
    update_establishment,
    toggle_establishment,
    EstablishmentNotFoundError,
)

router = APIRouter(prefix="/api/v1/establishments", tags=["establishments"])


@router.get("", response_model=list[EstablishmentResponse])
async def get_establishments(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("establishments:view")),
):
    return await list_establishments(db, current_user.company_id)


@router.post("", response_model=EstablishmentResponse, status_code=status.HTTP_201_CREATED)
async def post_establishment(
    payload: EstablishmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("establishments:manage")),
):
    return await create_establishment(db, current_user.company_id, payload.code, payload.name, payload.description)


@router.patch("/{establishment_id}", response_model=EstablishmentResponse)
async def patch_establishment(
    establishment_id: uuid.UUID,
    payload: EstablishmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("establishments:manage")),
):
    try:
        return await update_establishment(db, current_user.company_id, establishment_id, payload.code, payload.name, payload.description)
    except EstablishmentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{establishment_id}/toggle-status", response_model=EstablishmentResponse)
async def toggle_establishment_status(
    establishment_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("establishments:manage")),
):
    try:
        return await toggle_establishment(db, current_user.company_id, establishment_id)
    except EstablishmentNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))