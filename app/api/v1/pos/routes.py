"""
Routes for the POS/Caixa module - cash session open/close and checkout.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.activity import Activity
from app.models.stock import Stock
from app.services.point_of_sale_service import get_pos_or_raise
from app.schemas.cash_session import (
    OpenSessionRequest,
    CloseSessionRequest,
    CashSessionResponse,
    CheckoutRequest,
    LiquidatePendingInvoiceRequest,
    CreateProFormaRequest,
)
from app.schemas.invoice import InvoiceResponse, line_inputs
from app.services.cash_session_service import (
    open_session,
    close_session,
    get_open_session,
    get_carry_forward_amount,
    list_sessions,
    SessionAlreadyOpenError,
    SessionNotFoundError,
    SessionAlreadyClosedError,
    BilletageRequiredError,
)
from app.services.pos_service import checkout, liquidate_pending_invoice, create_pro_forma_from_pos, NoOpenSessionError
from app.services.invoice_service import ReferenceInvoiceTypeNotEligibleError
from app.api.v1.issuable import ensure_issuable, ensure_may_bill_later
from app.services.pos_documents_service import list_pos_documents
from app.services.point_of_sale_service import PosNotFoundError
from app.services.invoice_service import (
    ActivityNotFoundError,
    PeriodClosedError,
    EmptyInvoiceError,
    CustomerNotFoundError,
    ProductNotFoundError,
    StockUnavailableError,
    PaymentAmountMismatchError,
    DocumentTypeNotConfiguredError,
    SeriesNotConfiguredError,
    ProFormaNotFoundError,
    ProFormaAlreadyConvertedError,
)

from app.services.cash_session_service import ClosingDifferenceNotAllowedError, ClosingReasonRequiredError, get_session_summary

router = APIRouter(prefix="/api/v1/pos", tags=["pos"])



@router.post("/sessions/open", response_model=CashSessionResponse, status_code=status.HTTP_201_CREATED)
async def post_open_session(
    payload: OpenSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:open_session")),
):
    try:
        return await open_session(db, current_user.company_id, payload.pos_id, current_user, payload.opening_amount)
    except SessionAlreadyOpenError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PosNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("/sessions/open", response_model=CashSessionResponse | None)
async def get_current_open_session(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """Returns the currently open session for this POS, or null if none - lets the frontend know whether to show the checkout screen or the open-session prompt."""
    return await get_open_session(db, current_user.company_id, pos_id)


@router.get("/sessions/balance")
async def get_current_balance(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """Live expected cash balance for this POS's currently open session - not just
    the opening float, but opening + cash sales + net movements so far (same formula
    as close_session, computed on demand) - with its justification by payment method and movements, see
    cash_session_service.get_session_summary."""
    summary = await get_session_summary(db, current_user.company_id, pos_id)
    if summary is None:
        return {"balance": 0.0}
    return {"balance": summary["expected_cash"], **summary}  # balance: the cash expected in the drawer


@router.get("/sessions/carry-forward")
async def get_carry_forward(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """The amount that will automatically become the opening float if this POS's
    session is opened right now (last closed session's counted total, or 0) - lets
    the "Abrir caixa" confirmation show it before the cashier commits."""
    amount = await get_carry_forward_amount(db, current_user.company_id, pos_id)
    return {"amount": amount}


@router.post("/sessions/{session_id}/close", response_model=CashSessionResponse)
async def post_close_session(
    session_id: uuid.UUID,
    payload: CloseSessionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:close_session")),
):
    try:
        return await close_session(
            db, current_user.company_id, session_id, current_user.id,
            payload.closing_amount_counted, payload.closing_notes,
        )
    except SessionNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except SessionAlreadyClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except BilletageRequiredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ClosingDifferenceNotAllowedError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ClosingReasonRequiredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/sessions", response_model=list[CashSessionResponse])
async def get_sessions(
    activity_id: uuid.UUID | None = None,
    pos_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """Lists past cash sessions - history for review, optionally filtered by activity and/or POS."""
    return await list_sessions(db, current_user.company_id, activity_id, pos_id)


@router.post("/checkout/{pos_id}", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def post_checkout(
    pos_id: uuid.UUID,
    payload: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:checkout")),
):
    try:
        await ensure_issuable(db, payload.invoice_type, "pos")
        await ensure_may_bill_later(db, current_user, payload.invoice_type)
        return await checkout(
            db, current_user.company_id, pos_id, current_user, payload.customer_id,
            line_inputs(payload.lines),
            [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments],
            invoice_type=payload.invoice_type,
            discount_global_percent=payload.discount_global_percent,
            payment_term_id=payload.payment_term_id,
            payment_method_id=payload.payment_method_id,
            bank_account_id=payload.bank_account_id,
            due_date=payload.due_date,
        )
    except NoOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except EmptyInvoiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProductNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PaymentAmountMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except StockUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/pro-forma/{pos_id}", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def post_create_pro_forma(
    pos_id: uuid.UUID,
    payload: CreateProFormaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:proforma")),
):
    """Generates a Pro-forma (FP) from the Caixa screen - no payment, see pos_service.create_pro_forma_from_pos."""
    try:
        return await create_pro_forma_from_pos(
            db, current_user.company_id, pos_id, current_user, payload.customer_id,
            line_inputs(payload.lines),
            discount_global_percent=payload.discount_global_percent,
        )
    except NoOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.post("/liquidate/{pos_id}", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def post_liquidate_pending_invoice(
    pos_id: uuid.UUID,
    payload: LiquidatePendingInvoiceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:liquidate")),
):
    """Liquidates a pending Pro-forma from the Caixa screen - see NovaFatura/Invoices for the admin equivalent."""
    try:
        return await liquidate_pending_invoice(
            db, current_user.company_id, pos_id,
            payload.pro_forma_id, payload.target_invoice_type,
            [{"payment_method_id": p.payment_method_id, "amount": p.amount} for p in payload.payments],
        )
    except NoOpenSessionError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ProFormaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ProFormaAlreadyConvertedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PaymentAmountMismatchError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceTypeNotEligibleError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/documents/{pos_id}", response_model=list[InvoiceResponse])
async def get_pos_documents(
    pos_id: uuid.UUID,
    limit: int = 30,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """Documents shown by the Caixa: those of this cash point's sessions, plus the invoices still awaiting a payment."""
    return await list_pos_documents(db, current_user.company_id, pos_id, min(max(limit, 1), 100))



@router.get("/stock")
async def get_stock_of_point_of_sale(
    pos_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("pos:view")),
):
    """The stock the point of sale sells from (its activity's warehouse), for the till to warn before checkout."""
    from app.services.pos_service import get_pos_stock
    return await get_pos_stock(db, current_user.company_id, pos_id)
