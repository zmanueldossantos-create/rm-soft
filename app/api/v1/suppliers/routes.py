import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.supplier import SupplierCreateRequest, SupplierUpdateRequest, SupplierResponse
from app.services.supplier_service import (
    create_supplier, list_suppliers, update_supplier, toggle_supplier_status,
    SupplierNotFoundError, SupplierAlreadyExistsError,
)

router = APIRouter(prefix="/api/v1/suppliers", tags=["suppliers"])

# Managing the catalog (create/edit/toggle) is GESTOR's call. Listing is also
# needed by ARMAZENISTA (picks a supplier when recording a Guia de Entrada)
# and CONTABILISTA (reconciling purchase history) - see the roles audit
# discussion earlier this session.


@router.post("", response_model=SupplierResponse, status_code=status.HTTP_201_CREATED)
async def post_create_supplier(
    payload: SupplierCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("suppliers:manage")),
):
    try:
        return await create_supplier(
            db, current_user.company_id, payload.name, payload.nif, payload.phone_number,
            payload.email, payload.address, payload.payment_terms, payload.notes,
        )
    except SupplierAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=list[SupplierResponse])
async def get_suppliers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("suppliers:view")),
):
    return await list_suppliers(db, current_user.company_id)


@router.patch("/{supplier_id}", response_model=SupplierResponse)
async def patch_supplier(
    supplier_id: uuid.UUID,
    payload: SupplierUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("suppliers:manage")),
):
    try:
        return await update_supplier(
            db, current_user.company_id, supplier_id, payload.name, payload.nif, payload.phone_number,
            payload.email, payload.address, payload.payment_terms, payload.notes,
        )
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SupplierAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{supplier_id}/toggle", response_model=SupplierResponse)
async def post_toggle_supplier(
    supplier_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("suppliers:manage")),
):
    try:
        return await toggle_supplier_status(db, current_user.company_id, supplier_id)
    except SupplierNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
