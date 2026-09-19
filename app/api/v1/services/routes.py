"""
Service routes - scoped to the caller's company (Video 3).
Genuinely separate from Product (see decision on split model).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.service import ServiceCreateRequest, ServiceUpdateRequest, ServiceResponse
from app.services.service_service import (
    create_service,
    list_services,
    update_service,
    toggle_service_status,
    ServiceAlreadyExistsError,
    ServiceNotFoundError,
    ExemptionReasonRequiredError,
)

router = APIRouter(prefix="/api/v1/services", tags=["services"])


@router.post("", response_model=ServiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_service(
    payload: ServiceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("services:manage")),
):
    """Creates a service within the caller's company."""
    try:
        service = await create_service(
            db,
            company_id=current_user.company_id,
            code=payload.code,
            name=payload.name,
            vat_id=payload.vat_id,
            service_type_id=payload.service_type_id,
            resource_type_id=payload.resource_type_id,
            description=payload.description,
            unit_of_measure_id=payload.unit_of_measure_id,
            price=payload.price,
            brand=payload.brand,
            withholding_tax_id=payload.withholding_tax_id,
            subject_to_return=payload.subject_to_return,
            not_available_pos=payload.not_available_pos,
            status=payload.status,
            exemption_reason_id=payload.exemption_reason_id,
        )
    except ServiceAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ExemptionReasonRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return service


@router.get("", response_model=list[ServiceResponse])
async def get_services(
    db: AsyncSession = Depends(get_db),
    # CAIXA needs read access too - a cashier must see the service catalog to sell
    # (Caixa, Contas Abertas) even though only GESTOR can create/edit services.
    current_user: User = Depends(require_permission("services:view")),
):
    """Lists all services belonging to the caller's company."""
    return await list_services(db, current_user.company_id)


@router.patch("/{service_id}", response_model=ServiceResponse)
async def edit_service(
    service_id: uuid.UUID,
    payload: ServiceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("services:manage")),
):
    """Updates a service's editable fields, scoped to the caller's company."""
    try:
        service = await update_service(
            db,
            company_id=current_user.company_id,
            service_id=service_id,
            code=payload.code,
            name=payload.name,
            vat_id=payload.vat_id,
            service_type_id=payload.service_type_id,
            resource_type_id=payload.resource_type_id,
            description=payload.description,
            unit_of_measure_id=payload.unit_of_measure_id,
            price=payload.price,
            brand=payload.brand,
            withholding_tax_id=payload.withholding_tax_id,
            subject_to_return=payload.subject_to_return,
            not_available_pos=payload.not_available_pos,
            status=payload.status,
            exemption_reason_id=payload.exemption_reason_id,
        )
    except ServiceAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ServiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return service


@router.patch("/{service_id}/toggle-status", response_model=ServiceResponse)
async def toggle_status(
    service_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("services:manage")),
):
    """Activates or deactivates a service."""
    try:
        service = await toggle_service_status(db, current_user.company_id, service_id)
    except ServiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return service
