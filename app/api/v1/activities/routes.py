"""
Activity routes - business lines / points of sale within a Company.
GESTOR configures these (CAIXA needs read access to select one when
invoicing), but only for Modules the company has been granted by SUPER_ADMIN.
"""
from app.services.point_of_sale_service import PosPrintError
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.schemas.activity import ActivityCreateRequest, ActivityUpdateRequest, ActivityResponse
from app.schemas.module import ModuleResponse
from app.services.activity_service import (
    list_activities,
    create_activity,
    update_activity,
    toggle_activity_status,
    ActivityNotFoundError,
    ModuleNotGrantedError,
)
from app.services.company_module_service import list_company_modules
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


@router.get("/available-modules", response_model=list[ModuleResponse])
async def get_available_modules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("activities:manage")),
):
    """Lists the Modules the company has been granted by SUPER_ADMIN - to configure as Activities."""
    return await list_company_modules(db, current_user.company_id)


@router.post("", response_model=ActivityResponse, status_code=status.HTTP_201_CREATED)
async def create_new_activity(
    payload: ActivityCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("activities:manage")),
):
    """Configures a new activity for a Module the company has been granted."""
    try:
        return await create_activity(
            db, current_user.company_id, payload.module_id, payload.name
        )
    except ModuleNotGrantedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))


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
        return await create_point_of_sale(db, current_user.company_id, activity_id, payload.name, billetage_enabled=payload.billetage_enabled, print_after_sale=payload.print_after_sale, print_ticket=payload.print_ticket, print_a4=payload.print_a4, accept_closing_difference=payload.accept_closing_difference, print_closing_report=payload.print_closing_report)
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
            return await update_point_of_sale(db, current_user.company_id, pos_id, payload.name, billetage_enabled=payload.billetage_enabled, print_after_sale=payload.print_after_sale, print_ticket=payload.print_ticket, print_a4=payload.print_a4, accept_closing_difference=payload.accept_closing_difference, print_closing_report=payload.print_closing_report)
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
