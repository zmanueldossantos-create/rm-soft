"""
Activity routes - business lines within a Company and their caixas. An activity is never created here: each granted
module that sells gets its own by itself (activity_service.ensure_company_activities); the gestor renames it,
(de)activates it and manages its caixas (Tesouraria › Caixas).
"""
from app.services.point_of_sale_service import PosPrintError
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.activity import ActivityUpdateRequest, ActivityResponse
from app.services.activity_service import (
    list_activities,
    update_activity,
    toggle_activity_status,
    ActivityNotFoundError,
)
from app.schemas.pos import PosCreateRequest, PosUpdateRequest, PointOfSaleResponse
from app.services.point_of_sale_service import (
    list_points_of_sale,
    create_point_of_sale,
    update_point_of_sale,
    toggle_pos_status,
    PosAlreadyExistsError,
    PosNotFoundError,
)

from app.services.point_of_sale_service import DefaultPosNotModifiableError

router = APIRouter(prefix="/api/v1/activities", tags=["activities"])


@router.get("", response_model=list[ActivityResponse])
async def get_activities(
    db: AsyncSession = Depends(get_db),
    # ARMAZENISTA needs this too - Consumo Interno's activity tabs call this list.
    current_user: User = Depends(require_permission("activities:view")),
):
    """Lists the company's configured activities (e.g. Padaria, Bar, Hotel)."""
    return await list_activities(db, current_user.company_id)


@router.patch("/{activity_id}", response_model=ActivityResponse)
async def edit_activity(
    activity_id: uuid.UUID,
    payload: ActivityUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("activities:manage")),
):
    """Updates an activity's name and series code."""
    try:
        return await update_activity(db, current_user.company_id, activity_id, payload.name)
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/{activity_id}/toggle-status", response_model=ActivityResponse)
async def toggle_activity(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("activities:manage")),
):
    """Activates or deactivates an activity."""
    try:
        return await toggle_activity_status(db, current_user.company_id, activity_id)
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Points of Sale (nested under Activity) ----------

@router.get("/{activity_id}/pos", response_model=list[PointOfSaleResponse])
async def get_points_of_sale(
    activity_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos_terminals:view")),
):
    """Lists the POS configured under this activity (CAIXA needs this to pick one when opening the register)."""
    return await list_points_of_sale(db, current_user.company_id, activity_id)


@router.post("/{activity_id}/pos", response_model=PointOfSaleResponse, status_code=status.HTTP_201_CREATED)
async def create_new_pos(
    activity_id: uuid.UUID,
    payload: PosCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos_terminals:manage")),
):
    """Creates a new POS under this activity - several POS can share the same activity's stock/warehouse."""
    try:
        return await create_point_of_sale(db, current_user.company_id, activity_id, payload.name, billetage_enabled=payload.billetage_enabled, print_after_sale=payload.print_after_sale, print_ticket=payload.print_ticket, print_a4=payload.print_a4, accept_closing_difference=payload.accept_closing_difference, print_closing_report=payload.print_closing_report, allow_price_levels=payload.allow_price_levels, allow_free_price=payload.allow_free_price, kind=payload.kind)
    except PosPrintError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PosAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/pos/{pos_id}", response_model=PointOfSaleResponse)
async def edit_pos(
    pos_id: uuid.UUID,
    payload: PosUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos_terminals:manage")),
):
    """Renames a POS."""
    try:
        try:
            return await update_point_of_sale(db, current_user.company_id, pos_id, payload.name, billetage_enabled=payload.billetage_enabled, print_after_sale=payload.print_after_sale, print_ticket=payload.print_ticket, print_a4=payload.print_a4, accept_closing_difference=payload.accept_closing_difference, print_closing_report=payload.print_closing_report, allow_price_levels=payload.allow_price_levels, allow_free_price=payload.allow_free_price, kind=payload.kind)
        except PosPrintError as e:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
        except DefaultPosNotModifiableError as e:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PosAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/pos/{pos_id}/toggle-status", response_model=PointOfSaleResponse)
async def toggle_pos(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos_terminals:manage")),
):
    """Activates or deactivates a POS."""
    try:
        return await toggle_pos_status(db, current_user.company_id, pos_id)
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
