"""
Invoice routes - scoped to the caller's company (multi-tenant isolation, section 2.5 v7).
Priority #1 of the specification (section 1) - AGT fiscal compliance.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.invoice import Invoice, InvoiceStatus
from app.services.agt_queue import queue_for_agt
from app.services.invoice_service import (
    CashPointRequiredError, RefundNotAllowedError, attach_amount_due, get_credit_note_info, list_open_cash_points,
)
from datetime import date
from app.schemas.invoice import InvoiceCreateRequest, InvoiceResponse, InvoiceDetailResponse, CreditNoteCreateRequest, DebitNoteCreateRequest, ReceiptCreateRequest, ProFormaCreateRequest, OrcamentoCreateRequest, ConvertProFormaRequest, line_inputs
from app.services.cash_session_service import get_open_session_for_user
from app.services.invoice_service import (
    create_invoice,
    list_invoices,
    get_invoice_periods,
    get_invoice_with_lines,
    PeriodClosedError,
    ProductNotFoundError,
    CustomerNotFoundError,
    InvoiceNotFoundError,
    ActivityNotFoundError,
    EmptyInvoiceError,
    StockUnavailableError,
    DocumentTypeNotConfiguredError,
    SeriesNotConfiguredError,
    create_credit_note,
    ReferenceInvoiceNotFoundError,
    ReferenceInvoiceTypeNotEligibleError,
    ReferenceInvoiceAlreadyCancelledError,
    CreditNoteExceedsOriginalError,
    create_debit_note,
    create_receipt,
    ReceiptExceedsPendingError,
    create_pro_forma,
    convert_pro_forma_to_invoice,
    ProFormaNotFoundError,
    ProFormaAlreadyConvertedError,
    QuoteExpiredError,
    PaymentAmountMismatchError,
)

from app.api.v1.issuable import ensure_issuable

router = APIRouter(prefix="/api/v1/invoices", tags=["invoices"])



@router.post("", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_invoice(
    payload: InvoiceCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:issue")),
):
    """Creates an invoice with its lines, blocked if the fiscal period is closed."""
    await ensure_issuable(db, payload.invoice_type, "invoices")
    try:
        invoice = await create_invoice(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            customer_id=payload.customer_id,
            invoice_type=payload.invoice_type,
            business_date=payload.business_date,
            payment_term_id=payload.payment_term_id,
            payment_method_id=payload.payment_method_id,
            bank_account_id=payload.bank_account_id,
            due_date=payload.due_date,
            amount_received=payload.amount_received,
            cash_pos_id=payload.cash_pos_id,
            require_cash_point=True,
            enforce_document_rules=True,
            payment_date=payload.payment_date,
            observations=payload.observations,
            document_reference=payload.document_reference,
            discount_global_percent=payload.discount_global_percent,
            lines_input=line_inputs(payload.lines),
            prescription=payload.prescription.model_dump() if payload.prescription else None,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ProductNotFoundError, CustomerNotFoundError, EmptyInvoiceError, PaymentAmountMismatchError, CashPointRequiredError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except StockUnavailableError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return invoice


@router.post("/credit-note", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_credit_note(
    payload: CreditNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:credit_note")),
):
    """Creates a Nota de Credito against an already-issued Factura/Factura-Recibo - see Video 5."""
    try:
        credit_note = await create_credit_note(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            reference_invoice_id=payload.reference_invoice_id,
            credit_note_reason=payload.credit_note_reason,
            credit_note_cause=payload.credit_note_cause,
            lines_input=[{"invoice_line_id": l.invoice_line_id, "quantity": l.quantity} for l in payload.lines],
            restock=payload.restock,
            refunds=[{"payment_method_id": r.payment_method_id, "amount": r.amount} for r in payload.refunds],
            refund_pos_id=payload.refund_pos_id,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EmptyInvoiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReferenceInvoiceTypeNotEligibleError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceAlreadyCancelledError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (CreditNoteExceedsOriginalError, RefundNotAllowedError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return credit_note


@router.get("/{invoice_id}/credit-note-info")
async def credit_note_info(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:credit_note")),
):
    """What is left to credit per line, the refund figures and the cash points with an open session - for the NC screen."""
    try:
        return await get_credit_note_info(db, current_user.company_id, invoice_id)
    except ReferenceInvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/debit-note", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_debit_note(
    payload: DebitNoteCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:debit_note")),
):
    """Creates a Nota de Debito referencing an already-issued Factura/Factura-Recibo - see Video 5."""
    session = await get_open_session_for_user(db, current_user.company_id, current_user.id)
    try:
        debit_note = await create_debit_note(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            reference_invoice_id=payload.reference_invoice_id,
            customer_id=payload.customer_id,
            lines_input=line_inputs(payload.lines),
            document_reference=payload.document_reference,
            observations=payload.observations,
            cash_session_id=session.id if session else None,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (EmptyInvoiceError, ProductNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReferenceInvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReferenceInvoiceTypeNotEligibleError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceAlreadyCancelledError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return debit_note


@router.post("/receipt", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_receipt(
    payload: ReceiptCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:receipt")),
):
    """Creates a Recibo (payment acknowledgement) against an already-issued Factura/Factura-Recibo."""
    try:
        receipt = await create_receipt(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            reference_invoice_id=payload.reference_invoice_id,
            amount=payload.amount,
            document_reference=payload.document_reference,
            observations=payload.observations,
            payment_method_id=payload.payment_method_id,
            cash_pos_id=payload.cash_pos_id,
            require_cash_point=True,
            bank_account_id=payload.bank_account_id,
        )
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except EmptyInvoiceError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ReferenceInvoiceTypeNotEligibleError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except ReferenceInvoiceAlreadyCancelledError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except (ReceiptExceedsPendingError, CashPointRequiredError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return receipt


@router.post("/pro-forma", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_pro_forma(
    payload: ProFormaCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:proforma")),
):
    """Creates a Fatura Pro-forma (FP) - a non-fiscal quote, never submitted to AGT."""
    await ensure_issuable(db, "PRO_FORMA", "invoices")
    try:
        pro_forma = await create_pro_forma(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            customer_id=payload.customer_id,
            lines_input=line_inputs(payload.lines),
            document_reference=payload.document_reference,
            observations=payload.observations,
            discount_global_percent=payload.discount_global_percent,
        )
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (EmptyInvoiceError, ProductNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return pro_forma


@router.post("/orcamento", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def create_new_orcamento(
    payload: OrcamentoCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:quote")),
):
    """Creates an Orçamento (OR) - a quote to a customer, valid until a date; non-fiscal, never submitted to AGT."""
    await ensure_issuable(db, "ORCAMENTO", "invoices")
    try:
        quote = await create_pro_forma(
            db,
            company_id=current_user.company_id,
            activity_id=payload.activity_id,
            customer_id=payload.customer_id,
            lines_input=line_inputs(payload.lines),
            document_reference=payload.document_reference,
            observations=payload.observations,
            discount_global_percent=payload.discount_global_percent,
            invoice_type="ORCAMENTO",
            valid_until=payload.valid_until,
        )
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (EmptyInvoiceError, ProductNotFoundError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CustomerNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return quote


@router.post("/pro-forma/{item_id}/convert", response_model=InvoiceResponse, status_code=status.HTTP_201_CREATED)
async def convert_pro_forma(
    item_id: uuid.UUID,
    payload: ConvertProFormaRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:proforma_convert")),
):
    """Converts a Pro-forma into a real fiscal Factura/Factura-Recibo - see Kiami's "passar a FT/FR"."""
    try:
        invoice = await convert_pro_forma_to_invoice(
            db,
            company_id=current_user.company_id,
            pro_forma_id=item_id,
            target_invoice_type=payload.target_invoice_type,
            payment_term_id=payload.payment_term_id,
            payment_method_id=payload.payment_method_id,
            bank_account_id=payload.bank_account_id,
            due_date=payload.due_date,
        )
    except ProFormaNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (ProFormaAlreadyConvertedError, QuoteExpiredError) as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except StockUnavailableError as e:  # the invoice takes the goods out: not enough in the activity's warehouse
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except PeriodClosedError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except ActivityNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except (EmptyInvoiceError, ProductNotFoundError, ReferenceInvoiceTypeNotEligibleError) as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except DocumentTypeNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except SeriesNotConfiguredError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    return invoice


@router.get("", response_model=list[InvoiceResponse])
async def get_invoices(
    year: int | None = None,
    month: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    invoice_type: str | None = None,
    pending_only: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:view")),
):
    """Lists invoices belonging to the caller's company, filtered and paginated.
    invoice_type + pending_only=true finds pro-formas awaiting Caixa liquidation.
    CAIXA only sees documents from its own cash point (pro-formas excepted - see list_invoices
    docstring); GESTOR and other roles see everything, unrestricted."""
    pos_id = None
    if current_user.role == "CAIXA":
        from app.services.user_cash_point_access_service import get_access_for_user
        access = await get_access_for_user(db, current_user.company_id, current_user.id)
        pos_id = access.pos_id if access else None
    return await list_invoices(
        db, current_user.company_id, year, month, date_from, date_to, limit, offset,
        invoice_type=invoice_type, pending_only=pending_only, pos_id=pos_id,
    )


@router.get("/available-periods")
async def get_invoices_available_periods(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:view")),
):
    """Returns the distinct (year, month) pairs that have invoices - populates the Ano/Mes filters."""
    return await get_invoice_periods(db, current_user.company_id)


@router.get("/open-cash-points")
async def open_cash_points(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:view")),
):
    """The cash points with an open session and the cash they hold - where cash can enter or leave from Faturas."""
    return await list_open_cash_points(db, current_user.company_id)


@router.get("/{invoice_id}", response_model=InvoiceDetailResponse)
async def get_invoice_detail(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:view")),
):
    """Returns an invoice with its line items."""
    try:
        invoice, lines = await get_invoice_with_lines(db, current_user.company_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    await attach_amount_due(db, [invoice])
    return InvoiceDetailResponse(
        **InvoiceResponse.model_validate(invoice).model_dump(),
        lines=[l for l in lines],
    )


@router.get("/{invoice_id}/pdf")
async def download_invoice_pdf(
    invoice_id: uuid.UUID,
    format: str = "thermal",
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:view")),
):
    """Generates and returns the invoice PDF - format=thermal (80mm) or format=a4."""
    from app.services.invoice_pdf_service import render_invoice_pdf
    try:
        pdf_bytes, filename = await render_invoice_pdf(db, current_user.company_id, invoice_id, format)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/{invoice_id}/resubmit", response_model=InvoiceResponse)
async def resubmit_invoice(
    invoice_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("invoices:resubmit")),
):
    """
    Manually re-queues an invoice for AGT submission - the "Reenviar"
    button, for invoices stuck in ERRO (or PENDENTE if the worker missed
    the original task, e.g. after a restart). See retry policy in
    agt_worker.py.
    """
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == current_user.company_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fatura não encontrada")

    invoice.status = InvoiceStatus.PENDENTE
    await db.commit()
    await db.refresh(invoice)

    await queue_for_agt(db, invoice)
    return invoice
