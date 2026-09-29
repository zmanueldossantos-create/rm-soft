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
from app.models.company import Company
from app.models.customer import Customer
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.payment_term import PaymentTerm
from app.models.company_bank_account import CompanyBankAccount
from app.models.bank import Bank
from app.models.document_type import DocumentType
from num2words import num2words
from app.models.product import Product
from app.models.service import Service
from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
from app.models.invoice import Invoice, InvoiceStatus
from app.workers.agt_worker import submit_invoice_to_agt
from app.services.invoice_service import (
    CashPointRequiredError, RefundNotAllowedError, attach_amount_due, get_credit_note_info, list_open_cash_points,
)
from datetime import date
from app.schemas.invoice import InvoiceCreateRequest, InvoiceResponse, InvoiceDetailResponse, CreditNoteCreateRequest, DebitNoteCreateRequest, ReceiptCreateRequest, ProFormaCreateRequest, ConvertProFormaRequest
from app.utils.pdf_generator import generate_invoice_pdf_thermal, generate_invoice_pdf_a4
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
            lines_input=[{"product_id": l.product_id, "service_id": l.service_id, "quantity": l.quantity, "discount_percent": l.discount_percent} for l in payload.lines],
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
            lines_input=[{"product_id": l.product_id, "service_id": l.service_id, "quantity": l.quantity, "discount_percent": l.discount_percent} for l in payload.lines],
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
            lines_input=[{"product_id": l.product_id, "service_id": l.service_id, "quantity": l.quantity, "discount_percent": l.discount_percent} for l in payload.lines],
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
    except ProFormaAlreadyConvertedError as e:
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
    try:
        invoice, lines = await get_invoice_with_lines(db, current_user.company_id, invoice_id)
    except InvoiceNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))

    company_result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = company_result.scalar_one()

    customer = None
    if invoice.customer_id:
        customer_result = await db.execute(select(Customer).where(Customer.id == invoice.customer_id))
        customer_obj = customer_result.scalar_one_or_none()
        if customer_obj:
            customer = {"name": customer_obj.name, "nif": customer_obj.nif, "address": customer_obj.address}

    payment_method_name = None
    if invoice.payment_method_id:
        pm_result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.id == invoice.payment_method_id))
        pm = pm_result.scalar_one_or_none()
        payment_method_name = pm.name if pm else None

    payment_term_name = None
    if invoice.payment_term_id:
        pt_result = await db.execute(select(PaymentTerm).where(PaymentTerm.id == invoice.payment_term_id))
        pt = pt_result.scalar_one_or_none()
        payment_term_name = pt.name if pt else None

    # Show ALL of the company's active bank accounts, not just the one chosen for this
    # specific invoice - matches the Kiami reference, where the footer always lists every
    # known account regardless of which one the customer is expected to use.
    bank_accounts_result = await db.execute(
        select(CompanyBankAccount, Bank)
        .join(Bank, Bank.id == CompanyBankAccount.bank_id)
        .where(CompanyBankAccount.company_id == current_user.company_id, CompanyBankAccount.is_active == True)
    )
    bank_accounts_list = [
        {"acronym": bank.acronym, "account_number": ba.account_number, "iban": ba.iban}
        for ba, bank in bank_accounts_result.all()
    ]

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.id == invoice.document_type_id))
    doc_type_row = doc_type_result.scalar_one_or_none()
    is_fiscal_doc = doc_type_row.is_fiscal if doc_type_row else True

    # Amount in words (Kiami-style "Total: SEIS MILHOES E ...") - integer part only, since
    # AOA has no minor-unit convention commonly spelled out on these documents.
    total_int = int(round(float(invoice.total)))
    try:
        amount_in_words = num2words(total_int, lang="pt").upper() + " KWANZAS"
    except Exception:
        amount_in_words = None

    # Increment BEFORE building the "via" label so this very printout gets the correct
    # ordinal - the 1st ever call prints "Original", every one after that "Nº via" (see
    # print_count comment on the Invoice model for the legal requirement behind this).
    invoice.print_count = (invoice.print_count or 0) + 1
    await db.commit()


    INVOICE_TYPE_CODE = {
        "FACTURA": "FT", "FACTURA_RECIBO": "FR", "NOTA_CREDITO": "NC",
        "NOTA_DEBITO": "ND", "RECIBO": "RC", "PRO_FORMA": "FP",
    }

    # The referenced original invoice - RC/NC/ND all point back to one via reference_invoice_id.
    # RC (Recibo) needs it to render its own table row (it carries no product/service lines of its
    # own - see create_receipt docstring); NC/ND already had document_reference free text, but
    # fetching it directly here is more reliable than depending on that optional field.
    reference_invoice_dict = None
    if invoice.reference_invoice_id:
        ref_result = await db.execute(select(Invoice).where(Invoice.id == invoice.reference_invoice_id))
        ref_invoice = ref_result.scalar_one_or_none()
        if ref_invoice is not None:
            reference_invoice_dict = {
                "invoice_type": INVOICE_TYPE_CODE.get(ref_invoice.invoice_type.value, ref_invoice.invoice_type.value),
                "series": ref_invoice.series,
                "number": ref_invoice.number,
                "business_date": str(ref_invoice.business_date),
                "subtotal": float(ref_invoice.subtotal),
                "vat_total": float(ref_invoice.vat_total),
                "total": float(ref_invoice.total),
            }

    invoice_dict = {
        "invoice_type": INVOICE_TYPE_CODE.get(invoice.invoice_type.value, invoice.invoice_type.value),
        "series": invoice.series,
        "number": invoice.number,
        "number_digits": invoice.number_digits,
        "business_date": str(invoice.business_date),
        "due_date": str(invoice.due_date) if invoice.due_date else None,
        "payment_date": str(invoice.payment_date) if invoice.payment_date else None,
        "subtotal": float(invoice.subtotal),
        "vat_total": float(invoice.vat_total),
        "total": float(invoice.total),
        "retention_total": float(invoice.retention_total or 0),
        "discount_global_percent": float(invoice.discount_global_percent or 0),
        "document_reference": invoice.document_reference,
        "observations": invoice.observations,
        "payment_method_name": payment_method_name,
        "payment_term_name": payment_term_name,
        "print_count": invoice.print_count,
        "is_fiscal_doc": is_fiscal_doc,
        "amount_in_words": amount_in_words,
        "atcud": invoice.atcud,
        "invoice_hash": invoice.invoice_hash,
        "qr_code_data": invoice.qr_code_data,
        "reference_invoice": reference_invoice_dict,
    }
    product_ids = [l.product_id for l in lines if l.product_id]
    service_ids = [l.service_id for l in lines if l.service_id]
    products_by_id = {}
    if product_ids:
        products_result = await db.execute(select(Product).where(Product.id.in_(product_ids)))
        products_by_id = {p.id: p for p in products_result.scalars().all()}
    services_by_id = {}
    if service_ids:
        services_result = await db.execute(select(Service).where(Service.id.in_(service_ids)))
        services_by_id = {s.id: s for s in services_result.scalars().all()}
    # Products AND services carry a unit of measure (a service line used to print "-").
    unit_ids = [x.unit_of_measure_id for x in [*products_by_id.values(), *services_by_id.values()] if getattr(x, "unit_of_measure_id", None)]
    units_by_id = {}
    if unit_ids:
        units_result = await db.execute(select(UnitOfMeasureCatalog).where(UnitOfMeasureCatalog.id.in_(unit_ids)))
        units_by_id = {u.id: u for u in units_result.scalars().all()}

    lines_dict = []
    for l in lines:
        code = "-"
        unit = "-"
        if l.product_id and l.product_id in products_by_id:
            p = products_by_id[l.product_id]
            code = p.code
            if p.unit_of_measure_id and p.unit_of_measure_id in units_by_id:
                unit = units_by_id[p.unit_of_measure_id].code
        elif l.service_id and l.service_id in services_by_id:
            svc = services_by_id[l.service_id]
            code = svc.code
            svc_unit_id = getattr(svc, "unit_of_measure_id", None)
            if svc_unit_id and svc_unit_id in units_by_id:
                unit = units_by_id[svc_unit_id].code
        lines_dict.append({
            "code": code,
            "unit": unit,
            "product_name_snapshot": l.product_name_snapshot,
            "quantity": float(l.quantity),
            "unit_price": float(l.unit_price),
            "discount_percent": float(l.discount_percent or 0),
            "vat_rate_snapshot": float(l.vat_rate_snapshot),
            "line_subtotal": float(l.line_subtotal),
            "line_total": float(l.line_total),
            "exemption_code": l.exemption_code,
            "iec_amount": float(l.iec_amount or 0),
            "iselo_amount": float(l.iselo_amount or 0),
        })
    company_dict = {"name": company.name, "nif": company.nif, "address": company.address, "phone_number": company.phone_number, "phone_number_2": company.phone_number_2, "email": company.email, "website": company.website, "logo_path": company.logo_path, "bank_accounts": bank_accounts_list}

    if format == "a4":
        pdf_bytes = generate_invoice_pdf_a4(invoice_dict, lines_dict, company_dict, customer)
    else:
        pdf_bytes = generate_invoice_pdf_thermal(invoice_dict, lines_dict, company_dict, customer)

    filename = f"{invoice.series}-{invoice.number}-{format}.pdf"
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Fatura nao encontrada")

    invoice.status = InvoiceStatus.PENDENTE
    await db.commit()
    await db.refresh(invoice)

    submit_invoice_to_agt.delay(str(invoice.id))
    return invoice
