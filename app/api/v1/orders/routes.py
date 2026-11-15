"""Encomendas (capability ORDERS): the customers' orders - list by delivery date, create, change, production status,
cancel."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.customer_order import (
    CustomerOrderCancelRequest, CustomerOrderDeliverRequest, CustomerOrderPayRequest, CustomerOrderRequest,
    CustomerOrderStatusRequest,
)
from app.services.customer_order_service import (
    CustomerOrderError, CustomerOrderNotFoundError, cancel_info, cancel_order, create_order, deliver_order, list_orders,
    order_detail, order_options, pay_order, production_list, set_production_status, update_order,
)
from app.services.permission_service import has_permission

router = APIRouter(prefix="/api/v1/orders", tags=["orders"])


def _refused(e: CustomerOrderError) -> HTTPException:
    code = status.HTTP_404_NOT_FOUND if isinstance(e, CustomerOrderNotFoundError) else status.HTTP_422_UNPROCESSABLE_ENTITY
    return HTTPException(status_code=code, detail=str(e))


@router.get("")
async def get_orders(date_from: date | None = None, date_to: date | None = None, status_filter: str | None = None,
                     search: str | None = None, customer_id: uuid.UUID | None = None, activity_id: uuid.UUID | None = None,
                     db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("orders:view"))):
    try:
        return await list_orders(db, current_user.company_id, date_from, date_to, status_filter, search, customer_id,
                                 activity_id)
    except CustomerOrderError as e:
        raise _refused(e)


@router.get("/options")
async def get_order_options(db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:manage"))):
    return await order_options(db, current_user.company_id)


@router.get("/production-list")
async def get_production_list(day: date, activity_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("orders:view"))):
    """The production list of a day, in A4: what to make for the orders delivered that day."""
    from fastapi import Response
    from app.models.company import Company
    from app.services.cash_report_service import _company_dict
    from app.utils.production_list_pdf import generate_production_list_pdf
    data = await production_list(db, current_user.company_id, day, activity_id)
    company = await db.get(Company, current_user.company_id)
    pdf = generate_production_list_pdf(data, _company_dict(company))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="lista-producao_{day.isoformat()}.pdf"'})


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
        return await create_order(db, current_user.company_id, current_user.id, payload.model_dump(), user=current_user)
    except CustomerOrderError as e:
        raise _refused(e)


@router.put("/{order_id}")
async def put_order(order_id: uuid.UUID, payload: CustomerOrderRequest, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("orders:manage"))):
    try:
        return await update_order(db, current_user.company_id, order_id, payload.model_dump(), user=current_user)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/status")
async def post_order_status(order_id: uuid.UUID, payload: CustomerOrderStatusRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:production"))):
    try:
        return await set_production_status(db, current_user.company_id, order_id, payload.status)
    except CustomerOrderError as e:
        raise _refused(e)


@router.get("/{order_id}/cancel-info")
async def get_cancel_info(order_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("orders:manage"))):
    try:
        return await cancel_info(db, current_user.company_id, order_id)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/cancel")
async def post_order_cancel(order_id: uuid.UUID, payload: CustomerOrderCancelRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("orders:manage"))):
    # an invoiced order is cancelled with its credit note - and the deposit given back or kept: the gestor's decision
    may = await has_permission(db, current_user.company_id, current_user.role.value, "orders:cancel_invoiced")
    try:
        return await cancel_order(db, current_user.company_id, order_id, payload.reason, payload.deposit,
                                  payload.refund.model_dump() if payload.refund else None, may_cancel_invoiced=may)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/pay")
async def post_order_pay(order_id: uuid.UUID, payload: CustomerOrderPayRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("orders:charge"))):
    try:
        return await pay_order(db, current_user.company_id, current_user, order_id, payload.pos_id, payload.amount,
                               payload.payment_method_id, payload.terminal_id)
    except CustomerOrderError as e:
        raise _refused(e)


@router.post("/{order_id}/deliver")
async def post_order_deliver(order_id: uuid.UUID, payload: CustomerOrderDeliverRequest, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("orders:charge"))):
    try:
        return await deliver_order(db, current_user.company_id, current_user, order_id, payload.pos_id,
                                   payload.payment_method_id, payload.amount, payload.terminal_id, payload.on_credit)
    except CustomerOrderError as e:
        raise _refused(e)
