"""Kitchen screen (point 34c): the orders sent from the open accounts, and what the kitchen does with them."""
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models.user import User

from app.api.deps import require_permission
from app.schemas.kitchen import KitchenBoardResponse, KitchenLineActionRequest
from app.services.kitchen_service import KitchenItemNotFoundError, act_on_line, act_on_order, kitchen_board
from app.services.open_account_service import InvalidLineError

router = APIRouter(prefix="/api/v1/kitchen", tags=["kitchen"])


@router.get("/board", response_model=KitchenBoardResponse)
async def get_board(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("kitchen:view"))):
    return await kitchen_board(db, current_user.company_id)


@router.post("/lines/{line_id}/{action}", response_model=KitchenBoardResponse)
async def post_line_action(
    line_id: uuid.UUID,
    action: Literal["start", "ready", "refuse", "quantity"],
    payload: KitchenLineActionRequest | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("kitchen:update")),
):
    try:
        return await act_on_line(db, current_user.company_id, line_id, action, payload.quantity if payload else None)
    except KitchenItemNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidLineError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/orders/{order_id}/{action}", response_model=KitchenBoardResponse)
async def post_order_action(
    order_id: uuid.UUID,
    action: Literal["start_all", "ready_all"],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("kitchen:update")),
):
    try:
        return await act_on_order(db, current_user.company_id, order_id, action)
    except KitchenItemNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidLineError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
