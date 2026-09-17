"""
ServiceType routes - scoped to the caller's company (Video 3).
Managed by GESTOR only.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.models.user import User
from app.schemas.service_type import ServiceTypeRequest, ServiceTypeResponse
from app.services.service_type_service import (
    list_service_types,
    create_service_type,
    update_service_type,
    toggle_service_type,
    ServiceTypeNotFoundError,
    ServiceTypeAlreadyExistsError,
)

router = APIRouter(prefix="/api/v1/service-types", tags=["service-types"])
ALLOWED_ROLES = ("GESTOR",)


@router.get("", response_model=list[ServiceTypeResponse])
async def get_service_types(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    return await list_service_types(db, current_user.company_id)


@router.post("", response_model=ServiceTypeResponse, status_code=status.HTTP_201_CREATED)
async def post_service_type(
    payload: ServiceTypeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    try:
        return await create_service_type(
            db, current_user.company_id, payload.name,
            payload.not_available_purchases, payload.not_available_pos, payload.not_available_sales,
        )
    except ServiceTypeAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{service_type_id}", response_model=ServiceTypeResponse)
async def patch_service_type(
    service_type_id: uuid.UUID,
    payload: ServiceTypeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    try:
        return await update_service_type(
            db, current_user.company_id, service_type_id, payload.name,
            payload.not_available_purchases, payload.not_available_pos, payload.not_available_sales,
        )
    except ServiceTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ServiceTypeAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/{service_type_id}/toggle-status", response_model=ServiceTypeResponse)
async def toggle_service_type_status(
    service_type_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(*ALLOWED_ROLES)),
):
    try:
        return await toggle_service_type(db, current_user.company_id, service_type_id)
    except ServiceTypeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
