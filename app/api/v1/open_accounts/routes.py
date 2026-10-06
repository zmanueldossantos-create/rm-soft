import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.schemas.open_account import KitchenOrderResponse, OpenAccountLineUnitRequest
from app.services.open_account_service import InsufficientStockError, InvalidLineError, cancel_empty_account, change_line_unit, send_to_kitchen
from app.models.user import User
from app.schemas.open_account import (
    OpenAccountCreateRequest, OpenAccountResponse,
    OpenAccountLineCreateRequest, OpenAccountLineUpdateRequest, OpenAccountLineResponse,
    OpenAccountCloseRequest, OpenAccountTransferRequest, OpenAccountTransferResponse,
)
from app.services.open_account_service import (
    open_account, get_account_or_raise, list_open_accounts, list_account_lines,
    add_line, update_line_quantity, remove_line, close_account, transfer_lines,
    OpenAccountNotFoundError, AccountAlreadyClosedError, EmptyAccountError, ItemNotFoundError, InvalidTransferError,
)
from app.services.point_of_sale_service import PosNotFoundError
from app.services.resource_service import ResourceNotFoundError
from app.services.pos_service import NoOpenSessionError
from app.services.invoice_service import PaymentAmountMismatchError, StockUnavailableError, SeriesNotConfiguredError

router = APIRouter(prefix="/api/v1/open-accounts", tags=["open-accounts"])



@router.post("", response_model=OpenAccountResponse, status_code=status.HTTP_201_CREATED)
async def post_open_account(
    payload: OpenAccountCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:open")),
):
    try:
        return await open_account(
            db, current_user.company_id, payload.activity_id, payload.pos_id, current_user.id,
            payload.label, payload.resource_id, payload.customer_id, payload.notes,
        )
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("", response_model=list[OpenAccountResponse])
async def get_open_accounts(
    activity_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:view")),
):
    return await list_open_accounts(db, current_user.company_id, activity_id)


@router.get("/{account_id}", response_model=OpenAccountResponse)
async def get_open_account_detail(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:view")),
):
    try:
        return await get_account_or_raise(db, current_user.company_id, account_id)
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{account_id}/lines", response_model=list[OpenAccountLineResponse])
async def get_account_lines(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:view")),
):
    await get_account_or_raise(db, current_user.company_id, account_id)
    return await list_account_lines(db, account_id)


@router.post("/{account_id}/lines", response_model=OpenAccountLineResponse, status_code=status.HTTP_201_CREATED)
async def post_add_line(
    account_id: uuid.UUID,
    payload: OpenAccountLineCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:edit_lines")),
):
    try:
        return await add_line(
            db, current_user.company_id, account_id, current_user.id,
            payload.quantity, payload.product_id, payload.service_id, payload.sale_unit_id,
        )
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ItemNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidLineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{account_id}/lines/{line_id}", response_model=OpenAccountLineResponse | None)
async def patch_line_quantity(
    account_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: OpenAccountLineUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:edit_lines")),
):
    try:
        return await update_line_quantity(db, current_user.company_id, account_id, line_id, payload.quantity, current_user.id)
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ItemNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InsufficientStockError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidLineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.patch("/{account_id}/lines/{line_id}/unit", response_model=OpenAccountLineResponse)
async def patch_line_unit(
    account_id: uuid.UUID,
    line_id: uuid.UUID,
    payload: OpenAccountLineUnitRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:edit_lines")),
):
    """Sells the line in another unit (UN <-> CX), as the till cart's unit selector."""
    try:
        return await change_line_unit(db, current_user.company_id, account_id, line_id, payload.sale_unit_id)
    except (OpenAccountNotFoundError, ItemNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (AccountAlreadyClosedError, InsufficientStockError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidLineError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{account_id}/lines/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(
    account_id: uuid.UUID,
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:edit_lines")),
):
    try:
        await remove_line(db, current_user.company_id, account_id, line_id, current_user.id)
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidLineError as e:  # a dish the kitchen is already preparing
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{account_id}/close", response_model=OpenAccountResponse)
async def post_close_account(
    account_id: uuid.UUID,
    payload: OpenAccountCloseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:close")),
):
    try:
        payments = [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments]
        return await close_account(
            db, current_user.company_id, account_id, current_user, payments, payload.invoice_type, payload.pos_id,
        )
    except InvalidLineError as e:  # a till of another activity
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except EmptyAccountError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except NoOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PaymentAmountMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except StockUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{account_id}/transfer", response_model=OpenAccountTransferResponse)
async def post_transfer_lines(
    account_id: uuid.UUID,
    payload: OpenAccountTransferRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:transfer")),
):
    try:
        source, target, source_closed = await transfer_lines(
            db, current_user.company_id, account_id, current_user.id,
            [{"line_id": i.line_id, "quantity": i.quantity} for i in payload.items],
            payload.target_account_id, payload.target_resource_id, payload.new_label,
        )
    except (OpenAccountNotFoundError, ItemNotFoundError, ResourceNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AccountAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidTransferError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return OpenAccountTransferResponse(
        source_account=OpenAccountResponse.model_validate(source),
        target_account=OpenAccountResponse.model_validate(target),
        source_closed=source_closed,
    )


@router.post("/{account_id}/cancel", response_model=OpenAccountResponse)
async def post_cancel_empty_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:open")),
):
    """Cancels an account opened by mistake - only while it holds no article; no fiscal document is issued.
    Whoever may open an account may undo that mistake."""
    try:
        return await cancel_empty_account(db, current_user.company_id, account_id)
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (AccountAlreadyClosedError, InvalidLineError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/{account_id}/kitchen", response_model=KitchenOrderResponse, status_code=status.HTTP_201_CREATED)
async def post_send_to_kitchen(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("open_accounts:edit_lines")),
):
    """Sends every unsent dish of the account to the kitchen - one order, numbered for the day, signed by its sender."""
    try:
        return await send_to_kitchen(db, current_user.company_id, account_id, current_user.id)
    except OpenAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (AccountAlreadyClosedError, InvalidLineError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
