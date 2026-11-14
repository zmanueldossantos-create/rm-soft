"""
Routes for the Tesouraria module: CashMovementReason CRUD, CashMovement
create/list, and user <-> POS cash-point associations.

ARCHITECTURE NOTE: this used to also expose CashOffice routes (a separate
company-wide "Caixa Geral"). That concept has been retired - every Activity's
default POS (PointOfSale.is_default=True) now covers that role, managed
through the normal Activities/POS screens, not a dedicated endpoint here.
"""
import uuid
from typing import Literal
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.services.permission_service import has_permission
from app.models.user import User
from app.models.movement_type import MovementDirection
from app.models.cash_movement import CashMovementStatus, CashMovementType
from app.schemas.tesouraria import (
    CashMovementReasonCreateRequest,
    CashMovementReasonResponse,
    CashMovementCreateRequest,
    CashMovementResponse,
    CashMovementReceiveRequest,
    TransferBilletageLine,
    TreasuryPositionResponse,
    TreasuryMovement,
    TreasuryClosing,
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
    DestinationPosNotOpenError,
    MovementNotFoundError,
    MovementAlreadyReceivedError,
    MovementNotReceivableAtThisPosError,
    InsufficientFundsError,
    TransferBilletageRequiredError,
    get_transfer_billetage,
)
from app.services.cash_denomination_count_service import (
    CountSessionNotFoundError, CountTotalMismatchError, DenominationNotFoundError, EmptyCountError,
)

# the notes and coins of a transfer: what is wrong with them, and the status it answers with
BILLETAGE_ERRORS = {
    TransferBilletageRequiredError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    CountTotalMismatchError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    EmptyCountError: status.HTTP_422_UNPROCESSABLE_ENTITY,
    DenominationNotFoundError: status.HTTP_404_NOT_FOUND,
    CountSessionNotFoundError: status.HTTP_409_CONFLICT,
}


def _lines(lines) -> list[dict] | None:
    return [line.model_dump() for line in lines] if lines else None
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
from app.services.company_document_type_service import list_document_type_preferences, set_document_type_preference
from app.schemas.catalog import PaymentMethodPreferenceResponse, PaymentMethodPreferenceUpdateRequest, DocumentTypePreferenceResponse, DocumentTypePreferenceUpdateRequest
from app.schemas.tesouraria import DailyReportEntry
from app.services.daily_report_service import get_daily_report

from fastapi import Response
from app.services.cash_report_service import get_movements_report_data
from app.services.user_cash_point_access_service import require_cash_point_read_access
from app.services.point_of_sale_service import PosNotFoundError
from app.utils.cash_report_pdf import generate_movements_report_pdf

from app.services.treasury_overview_service import get_treasury_position, list_closings, list_treasury_movements
from app.schemas.tesouraria import (
    BankMovementCancelRequest, BankMovementCreateRequest, BankMovementResponse, BankOpeningBalanceRequest, BankPosition,
    BankStatement,
)
from app.services.bank_treasury_service import (
    BankAccountNotFoundError, BankMovementError, BankMovementNotFoundError, InvalidOpeningBalanceError,
    cancel_bank_movement, create_bank_movement, get_bank_statement, list_bank_positions, set_opening_balance,
)

router = APIRouter(prefix="/api/v1/tesouraria", tags=["tesouraria"])



# ---------- Cash movement reasons ----------

@router.get("/reasons", response_model=list[CashMovementReasonResponse])
async def get_cash_movement_reasons(
    direction: MovementDirection | None = None,
    usage: Literal["CAIXA", "BANCO"] | None = None,
    db: AsyncSession = Depends(get_db),
    # SUPER_ADMIN is also allowed - read-only exception for this one route, so
    # Configuracoes.jsx's catalog screen can list reasons. SUPER_ADMIN has no
    # company grants, hence also_allow_roles instead of a role permission.
    current_user: User = Depends(require_permission("tesouraria:reasons_view", also_allow_roles=("SUPER_ADMIN",))),
):
    return await list_cash_movement_reasons(db, current_user.company_id, direction, usage)


@router.post("/reasons", response_model=CashMovementReasonResponse, status_code=status.HTTP_201_CREATED)
async def create_new_cash_movement_reason(
    payload: CashMovementReasonCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:reasons_manage")),
):
    try:
        return await create_cash_movement_reason(
            db, current_user.company_id, payload.name, MovementDirection(payload.direction), payload.for_cash, payload.for_bank,
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
            db, current_user.company_id, reason_id, payload.name, MovementDirection(payload.direction),
            payload.for_cash, payload.for_bank,
        )
    except ReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidCashMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


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
    # a till transfers between tills and receives what is sent to it; cash crossing the company's border (a bank
    # withdrawal or deposit, an external entry or exit) is the gestor's - or a role given the right
    if payload.movement_type != CashMovementType.TRANSFERENCIA.value and not await has_permission(
            db, current_user.company_id, current_user.role.value, "tesouraria:external_movements"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                            detail="A caixa faz transferências entre caixas e recebe os fundos enviados - os levantamentos, "
                                   "depósitos e entradas/saídas externas registam-se pelo gestor")
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
            denomination_lines=_lines(payload.denomination_lines),
            bank_account_id=payload.bank_account_id,
        )
    except tuple(BILLETAGE_ERRORS) as e:
        raise HTTPException(status_code=BILLETAGE_ERRORS[type(e)], detail=str(e))
    except InvalidCashMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReasonNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReasonDirectionMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SourcePosNotOpenError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DestinationPosNotOpenError as e:
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


# ---------- Document type payment-term preferences (per-company override of requires_payment_term) ----------

@router.get("/document-type-payment-term-preferences", response_model=list[DocumentTypePreferenceResponse])
async def get_document_type_payment_term_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("documents:payment_term_prefs_view")),
):
    return await list_document_type_preferences(db, current_user.company_id)


@router.put("/document-type-payment-term-preferences/{document_type_id}", response_model=DocumentTypePreferenceResponse)
async def put_document_type_payment_term_preference(
    document_type_id: uuid.UUID,
    payload: DocumentTypePreferenceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("documents:payment_term_prefs_manage")),
):
    await set_document_type_preference(db, current_user.company_id, document_type_id, payload.requires_payment_term)
    updated = await list_document_type_preferences(db, current_user.company_id)
    return next(p for p in updated if p["id"] == document_type_id)


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
    payload: CashMovementReceiveRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:receive")),
):
    try:
        return await receive_cash_movement(db, current_user.company_id, movement_id, pos_id, current_user.id,
                                           denomination_lines=_lines(payload.denomination_lines) if payload else None)
    except tuple(BILLETAGE_ERRORS) as e:
        raise HTTPException(status_code=BILLETAGE_ERRORS[type(e)], detail=str(e))
    except DestinationPosNotOpenError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MovementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except MovementAlreadyReceivedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except MovementNotReceivableAtThisPosError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/movements/{movement_id}/billetage", response_model=list[TransferBilletageLine])
async def get_movement_billetage(
    movement_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:view")),
):
    """The notes and coins the sending till gave - proposed to the receiving till at the reception."""
    try:
        return await get_transfer_billetage(db, current_user.company_id, movement_id)
    except MovementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


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
        await cancel_cash_movement(db, current_user.company_id, movement_id, pos_id, can_cancel_entries=await has_permission(
            db, current_user.company_id, current_user.role.value, "tesouraria:external_movements"))
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
    try:
        await require_cash_point_read_access(db, current_user.company_id, current_user, pos_id)
    except CashPointAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return await get_daily_report(db, current_user.company_id, pos_id, date_from, date_to)


@router.get("/daily-report/pdf")
async def get_pos_daily_report_pdf(
    pos_id: uuid.UUID,
    date_from: date,
    date_to: date,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:daily_report")),
):
    """The movements report (A4 PDF) of a till over a period - the very lines of the journal shown on screen."""
    try:
        await require_cash_point_read_access(db, current_user.company_id, current_user, pos_id)
        data = await get_movements_report_data(db, current_user.company_id, pos_id, date_from, date_to)
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except CashPointAccessDeniedError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    return Response(content=generate_movements_report_pdf(data), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="movimentos-caixa-{date_from}-{date_to}.pdf"'})


# ---------- Tesouraria overview: the manager's read of every till (operations stay at the Caixa) ----------

@router.get("/overview/position", response_model=TreasuryPositionResponse)
async def get_overview_position(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await get_treasury_position(db, current_user.company_id)


@router.get("/overview/movements", response_model=list[TreasuryMovement])
async def get_overview_movements(
    date_from: date | None = None, date_to: date | None = None, pos_id: uuid.UUID | None = None,
    movement_type: CashMovementType | None = None, movement_status: CashMovementStatus | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await list_treasury_movements(db, current_user.company_id, date_from, date_to, pos_id, movement_type,
                                         movement_status)


@router.get("/overview/closings", response_model=list[TreasuryClosing])
async def get_overview_closings(
    date_from: date | None = None, date_to: date | None = None, pos_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await list_closings(db, current_user.company_id, date_from, date_to, pos_id)


# ---------- Bancos: the balance and the statement of each bank account (Tesouraria, with or without accounting) ----------

@router.get("/banks", response_model=list[BankPosition])
async def get_banks(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await list_bank_positions(db, current_user.company_id)


@router.get("/banks/{account_id}/statement", response_model=BankStatement)
async def get_bank_account_statement(
    account_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    try:
        return await get_bank_statement(db, current_user.company_id, account_id, date_from, date_to)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/banks/{account_id}/opening", response_model=BankPosition)
async def put_bank_opening_balance(
    account_id: uuid.UUID, payload: BankOpeningBalanceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:banks_manage")),
):
    try:
        await set_opening_balance(db, current_user.company_id, account_id, payload.amount, payload.opening_date)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidOpeningBalanceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return next(b for b in await list_bank_positions(db, current_user.company_id) if b["id"] == account_id)


@router.post("/banks/{account_id}/movements", response_model=BankMovementResponse, status_code=status.HTTP_201_CREATED)
async def post_bank_movement(
    account_id: uuid.UUID, payload: BankMovementCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:bank_movements")),
):
    try:
        return await create_bank_movement(db, current_user.company_id, current_user, account_id, payload.reason_id,
                                          payload.amount, payload.movement_date, payload.reference, payload.description)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BankMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/bank-movements/{movement_id}/cancel", response_model=BankMovementResponse)
async def post_cancel_bank_movement(
    movement_id: uuid.UUID, payload: BankMovementCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:bank_movements")),
):
    try:
        return await cancel_bank_movement(db, current_user.company_id, movement_id, current_user, payload.reason)
    except BankMovementNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BankMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ---------- Terminais: TPA / Multicaixa Express - the bank account a card payment at the till lands on ----------

from app.schemas.tesouraria import PaymentTerminalRequest, PaymentTerminalResponse  # noqa: E402
from app.services.payment_terminal_service import (  # noqa: E402
    PaymentTerminalError, PaymentTerminalNotFoundError, create_terminal, list_terminals, toggle_terminal,
    update_terminal,
)


@router.get("/terminals", response_model=list[PaymentTerminalResponse])
async def get_terminals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await list_terminals(db, current_user.company_id)


@router.post("/terminals", response_model=PaymentTerminalResponse, status_code=status.HTTP_201_CREATED)
async def post_terminal(
    payload: PaymentTerminalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:banks_manage")),
):
    try:
        return await create_terminal(db, current_user.company_id, payload.name, payload.kind, payload.bank_account_id,
                                     payload.pos_id, payload.payment_method_ids)
    except PaymentTerminalError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.put("/terminals/{terminal_id}", response_model=PaymentTerminalResponse)
async def put_terminal(
    terminal_id: uuid.UUID, payload: PaymentTerminalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:banks_manage")),
):
    try:
        return await update_terminal(db, current_user.company_id, terminal_id, payload.name, payload.kind,
                                     payload.bank_account_id, payload.pos_id, payload.payment_method_ids)
    except PaymentTerminalNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PaymentTerminalError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/terminals/{terminal_id}/toggle-status", response_model=PaymentTerminalResponse)
async def patch_toggle_terminal(
    terminal_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:banks_manage")),
):
    try:
        return await toggle_terminal(db, current_user.company_id, terminal_id)
    except PaymentTerminalNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Transferências: between two bank accounts of the company (em trânsito between two banks) ----------

from app.schemas.tesouraria import (  # noqa: E402
    BankTransferConfirmRequest, BankTransferCreateRequest, BankTransferResponse,
)
from app.services.bank_transfer_service import (  # noqa: E402
    BankTransferNotFoundError, cancel_bank_transfer, confirm_funds_available, create_bank_transfer,
    describe_transfers, list_transfers_in_transit,
)


@router.get("/bank-transfers/in-transit", response_model=list[BankTransferResponse])
async def get_transfers_in_transit(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:overview")),
):
    return await list_transfers_in_transit(db, current_user.company_id)


@router.post("/banks/{account_id}/transfers", response_model=BankTransferResponse, status_code=status.HTTP_201_CREATED)
async def post_bank_transfer(
    account_id: uuid.UUID, payload: BankTransferCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:bank_movements")),
):
    try:
        transfer = await create_bank_transfer(db, current_user.company_id, current_user, account_id, payload.to_account_id,
                                              payload.amount, payload.transfer_date, payload.reference, payload.description)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BankMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return (await describe_transfers(db, [transfer]))[0]


@router.post("/bank-transfers/{transfer_id}/available", response_model=BankTransferResponse)
async def post_funds_available(
    transfer_id: uuid.UUID, payload: BankTransferConfirmRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:bank_movements")),
):
    try:
        transfer = await confirm_funds_available(db, current_user.company_id, transfer_id, current_user, payload.available_date)
    except BankTransferNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BankMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return (await describe_transfers(db, [transfer]))[0]


@router.post("/bank-transfers/{transfer_id}/cancel", response_model=BankTransferResponse)
async def post_cancel_bank_transfer(
    transfer_id: uuid.UUID, payload: BankMovementCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("tesouraria:bank_movements")),
):
    try:
        transfer = await cancel_bank_transfer(db, current_user.company_id, transfer_id, current_user, payload.reason)
    except BankTransferNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except BankMovementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return (await describe_transfers(db, [transfer]))[0]
