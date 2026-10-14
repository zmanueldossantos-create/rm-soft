"""Faturas de compra (point 12): register the supplier invoices, read them, cancel a mistaken registration."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.purchase_invoice import PurchaseInvoiceStatus
from app.models.user import User
from app.schemas.purchase_invoice import PurchaseInvoiceCancelRequest, PurchaseInvoiceCreateRequest
from app.services.fiscal_period_service import PeriodClosedError
from app.services.permission_service import has_permission
from app.services.purchase_invoice_service import (
    PurchaseInvoiceError, PurchaseInvoiceNotFoundError, cancel_purchase_invoice, get_purchase_invoice,
    list_purchase_invoices, register_purchase_invoice,
)

router = APIRouter(prefix="/api/v1/purchases", tags=["purchases"])

ERRORS = {PurchaseInvoiceError: status.HTTP_422_UNPROCESSABLE_ENTITY, PeriodClosedError: status.HTTP_409_CONFLICT,
          PurchaseInvoiceNotFoundError: status.HTTP_404_NOT_FOUND}


def _http(e: Exception) -> HTTPException:
    return HTTPException(status_code=ERRORS[type(e)], detail=str(e))


@router.get("")
async def get_purchase_invoices(
    supplier_id: uuid.UUID | None = None, fiscal_period_id: uuid.UUID | None = None,
    invoice_status: PurchaseInvoiceStatus | None = None, date_from: date | None = None, date_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("purchases:view")),
):
    return await list_purchase_invoices(db, current_user.company_id, supplier_id, fiscal_period_id, invoice_status,
                                        date_from, date_to)


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_purchase_invoice(
    payload: PurchaseInvoiceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("purchases:manage")),
):
    # bringing the goods into a warehouse is a stock reception: it needs that permission too
    if payload.stock_entry and not await has_permission(db, current_user.company_id, current_user.role.value, "stock:receive"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Não tem permissão para dar entrada em stock")
    try:
        invoice = await register_purchase_invoice(
            db, current_user.company_id, current_user.id, payload.supplier_id, payload.supplier_document,
            payload.document_date, [l.model_dump() for l in payload.lines], payload.fiscal_period_id,
            payload.due_date, payload.description, payload.stock_entry, payload.warehouse_id,
        )
        return await get_purchase_invoice(db, current_user.company_id, invoice.id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.get("/{invoice_id}")
async def get_one_purchase_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("purchases:view")),
):
    try:
        return await get_purchase_invoice(db, current_user.company_id, invoice_id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.post("/{invoice_id}/cancel")
async def post_cancel_purchase_invoice(
    invoice_id: uuid.UUID,
    payload: PurchaseInvoiceCancelRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("purchases:manage")),
):
    try:
        await cancel_purchase_invoice(db, current_user.company_id, invoice_id, current_user.id, payload.reason)
        return await get_purchase_invoice(db, current_user.company_id, invoice_id)
    except tuple(ERRORS) as e:
        raise _http(e)
