"""Pagamentos a fornecedores (point 3): pay invoices of a supplier, list, read, print and cancel the payments; each
supplier's balance and conta corrente."""
import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.company import Company
from app.models.user import User
from app.services.supplier_payment_service import (
    SupplierPaymentError, SupplierPaymentNotFoundError, cancel_supplier_payment, create_supplier_payment,
    get_supplier_payment, list_supplier_payments, supplier_balances, supplier_statement,
)

router = APIRouter(prefix="/api/v1/supplier-payments", tags=["supplier-payments"])

ERRORS = {SupplierPaymentError: status.HTTP_422_UNPROCESSABLE_ENTITY, SupplierPaymentNotFoundError: status.HTTP_404_NOT_FOUND}


class AllocationInput(BaseModel):
    purchase_invoice_id: uuid.UUID
    amount: float


class SupplierPaymentCreateRequest(BaseModel):
    supplier_id: uuid.UUID
    payment_method_id: uuid.UUID
    payment_date: date | None = None
    bank_account_id: uuid.UUID | None = None  # a bank method
    pos_id: uuid.UUID | None = None  # cash: the till it leaves
    reference: str | None = None  # cheque or transfer number
    notes: str | None = None
    allocations: list[AllocationInput]


class CancelRequest(BaseModel):
    reason: str


def _http(e: Exception) -> HTTPException:
    return HTTPException(status_code=ERRORS[type(e)], detail=str(e))


async def _company(db: AsyncSession, company_id) -> dict:
    from app.services.cash_report_service import _company_dict
    return _company_dict((await db.execute(select(Company).where(Company.id == company_id))).scalar_one())


def _pdf(content: bytes, name: str) -> Response:
    return Response(content=content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="{name}.pdf"'})


@router.get("")
async def get_payments(supplier_id: uuid.UUID | None = None, payment_status: str | None = None,
                       date_from: date | None = None, date_to: date | None = None, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("purchases:view"))):
    return await list_supplier_payments(db, current_user.company_id, supplier_id, payment_status, date_from, date_to)


@router.post("", status_code=status.HTTP_201_CREATED)
async def post_payment(payload: SupplierPaymentCreateRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("purchases:pay"))):
    try:
        payment = await create_supplier_payment(
            db, current_user.company_id, current_user, payload.supplier_id, [a.model_dump() for a in payload.allocations],
            payload.payment_method_id, payload.payment_date, payload.bank_account_id, payload.pos_id, payload.reference,
            payload.notes,
        )
        return await get_supplier_payment(db, current_user.company_id, payment.id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.get("/balances")
async def get_balances(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("purchases:view"))):
    """{supplier id: what the company owes it}."""
    return {str(k): v for k, v in (await supplier_balances(db, current_user.company_id)).items()}


@router.get("/statement/{supplier_id}")
async def get_statement(supplier_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
                        db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("purchases:view"))):
    try:
        return await supplier_statement(db, current_user.company_id, supplier_id, date_from, date_to)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.get("/statement/{supplier_id}/pdf")
async def get_statement_pdf(supplier_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
                            db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("purchases:view"))):
    from app.utils.supplier_payment_pdf import generate_supplier_statement_pdf
    try:
        data = await supplier_statement(db, current_user.company_id, supplier_id, date_from, date_to)
    except tuple(ERRORS) as e:
        raise _http(e)
    return _pdf(generate_supplier_statement_pdf(data, await _company(db, current_user.company_id)), "conta-corrente")


@router.get("/{payment_id}")
async def get_payment(payment_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("purchases:view"))):
    try:
        return await get_supplier_payment(db, current_user.company_id, payment_id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.post("/{payment_id}/cancel")
async def post_cancel(payment_id: uuid.UUID, payload: CancelRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("purchases:pay"))):
    try:
        await cancel_supplier_payment(db, current_user.company_id, payment_id, current_user, payload.reason)
        return await get_supplier_payment(db, current_user.company_id, payment_id)
    except tuple(ERRORS) as e:
        raise _http(e)


@router.get("/{payment_id}/pdf")
async def get_payment_pdf(payment_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("purchases:view"))):
    from app.utils.supplier_payment_pdf import generate_supplier_payment_pdf
    try:
        data = await get_supplier_payment(db, current_user.company_id, payment_id)
    except tuple(ERRORS) as e:
        raise _http(e)
    return _pdf(generate_supplier_payment_pdf(data, await _company(db, current_user.company_id)),
                data["reference"].replace("/", "-"))
