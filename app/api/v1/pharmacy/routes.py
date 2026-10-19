"""
Farmácia routes - the context of the product form (is the Farmácia on, the forms, the medicine exemption motive) and
the GESTOR's list of pharmaceutical forms. Scoped to the caller's company.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.services.pharmacy_service import (
    MedicineError, PharmaceuticalFormAlreadyExistsError, PharmaceuticalFormNotFoundError, create_form, list_forms,
    pharmacy_context, toggle_form, update_form,
)

router = APIRouter(prefix="/api/v1/pharmacy", tags=["pharmacy"])


class PharmaceuticalFormRequest(BaseModel):
    name: str


class PharmaceuticalFormResponse(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool

    class Config:
        from_attributes = True


@router.get("/context")
async def get_pharmacy_context(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("products:view")),
):
    """Is the Farmácia on for the company, its pharmaceutical forms and the exemption motive proposed for a medicine."""
    return await pharmacy_context(db, current_user.company_id)


@router.get("/forms", response_model=list[PharmaceuticalFormResponse])
async def get_forms(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:view")),
):
    return await list_forms(db, current_user.company_id)


@router.post("/forms", response_model=PharmaceuticalFormResponse, status_code=status.HTTP_201_CREATED)
async def post_form(
    payload: PharmaceuticalFormRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await create_form(db, current_user.company_id, payload.name)
    except PharmaceuticalFormAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MedicineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/forms/{form_id}", response_model=PharmaceuticalFormResponse)
async def patch_form(
    form_id: uuid.UUID,
    payload: PharmaceuticalFormRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await update_form(db, current_user.company_id, form_id, payload.name)
    except PharmaceuticalFormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PharmaceuticalFormAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MedicineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/forms/{form_id}/toggle-status", response_model=PharmaceuticalFormResponse)
async def patch_form_status(
    form_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pharmaceutical_forms:manage")),
):
    try:
        return await toggle_form(db, current_user.company_id, form_id)
    except PharmaceuticalFormNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
