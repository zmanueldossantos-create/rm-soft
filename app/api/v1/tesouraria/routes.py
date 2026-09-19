"""
Routes for the Tesouraria module: CashMovementReason CRUD, CashMovement
create/list, and user <-> POS cash-point associations.

ARCHITECTURE NOTE: this used to also expose CashOffice routes (a separate
company-wide "Caixa Geral"). That concept has been retired - every Activity's
default POS (PointOfSale.is_default=True) now covers that role, managed
through the normal Activities/POS screens, not a dedicated endpoint here.
"""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.movement_type import MovementDirection
from app.models.cash_movement import CashMovementType
from app.schemas.tesouraria import (
    CashMovementReasonCreateRequest,
    CashMovementReasonResponse,
    CashMovementCreateRequest,
    CashMovementResponse,
    AssignCashPointRequest,
    UserCashPointAccessResponse,
)
from app.services.cash_movement_service import (
    list_cash_movement_reasons,
    create_cash_movement_reason,
    update_cash_movement_reason,
    toggle_reason_status,
    create_cash_movement,
    list_cash_movements,
    receive_cash_movement,
    list_pending_receptions,
    list_pending_emissions,
    cancel_cash_movement,
    ReasonNotFoundError,
    InvalidCashMovementError,
    ReasonDirectionMismatchError,
    SourcePosNotOpenError,
    MovementNotFoundError,
    MovementAlreadyReceivedError,
    MovementNotReceivableAtThisPosError,
    InsufficientFundsError,
)
from app.services.user_cash_point_access_service import CashPointAccessDeniedError
from app.services.point_of_sale_service import PosNotFoundError
from app.services.user_cash_point_access_service import (
    list_cash_point_access,
    assign_user_to_cash_point,
    unassign_user,
    UserNotFoundError,
    AccessNotFoundError,
)
from app.services.company_payment_method_service import list_payment_method_preferences, set_payment_method_preference
from app.schemas.catalog import PaymentMethodPreferenceResponse, PaymentMethodPreferenceUpdateRequest
from app.schemas.tesouraria import DailyReportEntry
from app.services.daily_report_service import get_daily_report

router = APIRouter(prefix="/api/v1/tesouraria", tags=["tesouraria"])



# ---------- Cash movement reasons ----------

@router.get("/reasons", response_model=list[CashMovementReasonResponse])
async def get_cash_movement_reasons(
    direction: MovementDirection | None = None,
    db: AsyncSession = Depends(get_db),
    # SUPER_ADMIN is also allowed - read-only exception for this one route, so
    # Configuracoes.jsx's catalog screen can list reasons. SUPER_ADMIN has no
    # company grants, hence also_allow_roles instead of a role permission.
    current_user: User = Depends(require_permission("tesouraria:reasons_view", also_allow_roles=("SUPER_ADMIN",))),
):
    return await list_cash_movement_reasons(db, current_user.company_id, direction)


@router.post("/reasons", response_model=CashMovementReasonResponse, status_code=status.HTTP_201_CREATED)
async def create_new_cash_movement_reason(
    payload: CashMovementReasonCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:reasons_manage")),
):
    try:
        return await create_cash_movement_reason(
            db, current_user.company_id, payload.name, MovementDirection(payload.direction)
        )
    except InvalidCashMovementError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.patch("/reasons/{reason_id}", response_model=CashMovementReasonResponse)
async def edit_cash_movement_reason(
    reason_id: uuid.UUID,
    payload: CashMovementReasonCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:reasons_manage")),
):
    try:
        return await update_cash_movement_reason(
            db, current_user.company_id, reason_id, payload.name, MovementDirection(payload.direction)
        )
    except ReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/reasons/{reason_id}/toggle-status", response_model=CashMovementReasonResponse)
async def toggle_cash_movement_reason(
    reason_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:reasons_manage")),
):
    try:
        return await toggle_reason_status(db, current_user.company_id, reason_id)
    except ReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Cash movements ----------

@router.post("", response_model=CashMovementResponse, status_code=status.HTTP_201_CREATED)
async def post_cash_movement(
    payload: CashMovementCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:record")),
):
    try:
        return await create_cash_movement(
            db, current_user.company_id,
            movement_type=CashMovementType(payload.movement_type),
            creating_user=current_user,
            amount=payload.amount,
            source_pos_id=payload.source_pos_id,
            destination_pos_id=payload.destination_pos_id,
            reason_id=payload.reason_id,
            movement_date=payload.movement_date,
            description=payload.description,
        )
    except InvalidCashMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReasonDirectionMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SourcePosNotOpenError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InsufficientFundsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CashPointAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=list[CashMovementResponse])
async def get_cash_movements(
    pos_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:view")),
):
    return await list_cash_movements(db, current_user.company_id, pos_id)


# ---------- User <-> POS cash-point associations ----------

@router.get("/my-association", response_model=UserCashPointAccessResponse | None)
async def get_my_cash_point_association(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:my_association")),
):
    """Any authenticated (non-SUPER_ADMIN) user can check their own association -
    used by Caixa.jsx to know which POS to lock onto / whether to show the picker."""
    from app.services.user_cash_point_access_service import get_access_for_user
    return await get_access_for_user(db, current_user.company_id, current_user.id)


@router.get("/associations", response_model=list[UserCashPointAccessResponse])
async def get_cash_point_associations(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:associations_manage")),
):
    return await list_cash_point_access(db, current_user.company_id)


@router.put("/associations/{user_id}", response_model=UserCashPointAccessResponse)
async def put_cash_point_association(
    user_id: uuid.UUID,
    payload: AssignCashPointRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:associations_manage")),
):
    """Assigns (or reassigns) a user to exactly one POS."""
    try:
        return await assign_user_to_cash_point(db, current_user.company_id, user_id, payload.pos_id)
    except UserNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.delete("/associations/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_cash_point_association(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:associations_manage")),
):
    try:
        await unassign_user(db, current_user.company_id, user_id)
    except AccessNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Company payment method preferences (which of the 12 AGT codes show at this company's Caixa) ----------

@router.get("/payment-method-preferences", response_model=list[PaymentMethodPreferenceResponse])
async def get_payment_method_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:payment_prefs_view")),
):
    return await list_payment_method_preferences(db, current_user.company_id)


@router.put("/payment-method-preferences/{payment_method_id}", response_model=PaymentMethodPreferenceResponse)
async def put_payment_method_preference(
    payment_method_id: uuid.UUID,
    payload: PaymentMethodPreferenceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:payment_prefs_manage")),
):
    await set_payment_method_preference(db, current_user.company_id, payment_method_id, payload.available_at_pos)
    updated = await list_payment_method_preferences(db, current_user.company_id)
    return next(p for p in updated if p["id"] == payment_method_id)


# ---------- Cash movement reception (two-step transfer confirmation) ----------

@router.get("/pending-receptions/{pos_id}", response_model=list[CashMovementResponse])
async def get_pending_receptions(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:view")),
):
    return await list_pending_receptions(db, current_user.company_id, pos_id)


@router.post("/movements/{movement_id}/receive", response_model=CashMovementResponse)
async def post_receive_movement(
    movement_id: uuid.UUID,
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:receive")),
):
    try:
        return await receive_cash_movement(db, current_user.company_id, movement_id, pos_id, current_user.id)
    except MovementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MovementAlreadyReceivedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MovementNotReceivableAtThisPosError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/pending-emissions/{pos_id}", response_model=list[CashMovementResponse])
async def get_pending_emissions(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:view")),
):
    return await list_pending_emissions(db, current_user.company_id, pos_id)


@router.delete("/movements/{movement_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pending_movement(
    movement_id: uuid.UUID,
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:cancel_movement")),
):
    try:
        await cancel_cash_movement(db, current_user.company_id, movement_id, pos_id)
    except MovementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MovementAlreadyReceivedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MovementNotReceivableAtThisPosError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/daily-report", response_model=list[DailyReportEntry])
async def get_pos_daily_report(
    pos_id: uuid.UUID,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:daily_report")),
):
    return await get_daily_report(db, current_user.company_id, pos_id, date_from, date_to)
