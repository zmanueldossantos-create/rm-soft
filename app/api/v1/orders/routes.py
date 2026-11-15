"""Encomendas (capability ORDERS): the customers' orders - list by delivery date, create, change, production status,
cancel."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.customer_order import CustomerOrderCancelRequest, CustomerOrderRequest, CustomerOrderStatusRequest
from app.services.customer_order_service import (
    CustomerOrderError, CustomerOrderNotFoundError, cancel_order, create_order, list_orders, order_detail, order_options,
    set_production_status, update_order,
)

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _refused(e: CustomerOrderError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(e, CustomerOrderNotFoundError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(e))


@router.get("")
async def get_orders(date_from: date | None = None, date_to: date | None = None, status_filter: str | None = None,
                     search: str | None = None, customer_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_permission("orders:view"))):
    try:
        return await list_orders(db, current_user.company_id, date_from, date_to, status_filter, search, customer_id)
    except CustomerOrderError as e:
        raise _refused(e)


@router.get("/options")
async def get_order_options(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:manage"))):
    return await order_options(db, current_user.company_id)


@router.get("/{order_id}")
async def get_order(order_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("orders:view"))):
    try:
        return await order_detail(db, current_user.company_id, order_id)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_order(payload: CustomerOrderRequest, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_permission("orders:manage"))):
    try:
        return await create_order(db, current_user.company_id, current_user.id, payload.model_dump())
    except CustomerOrderError as e:
        raise _refused(e)


@router.put("/{order_id}")
async def put_order(order_id: uuid.UUID, payload: CustomerOrderRequest, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("orders:manage"))):
    try:
        return await update_order(db, current_user.company_id, order_id, payload.model_dump())
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/status")
async def post_order_status(order_id: uuid.UUID, payload: CustomerOrderStatusRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:production"))):
    try:
        return await set_production_status(db, current_user.company_id, order_id, payload.status)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/cancel")
async def post_order_cancel(order_id: uuid.UUID, payload: CustomerOrderCancelRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:manage"))):
    try:
        return await cancel_order(db, current_user.company_id, order_id, payload.reason)
    except CustomerOrderError as e:
        raise _refused(e)
