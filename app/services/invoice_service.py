"""
Business logic for invoice creation.
See specification v6/v7, section 4 (Priority #1 - AGT fiscal compliance).

Enforces:
- Period/Year lock check before any invoice is created (section 3.4/3.5).
- Sequential invoice numbering per (company, series) - never reused, never skipped.
- VAT breakdown computed per line from each product's current VAT rate,
  snapshotted onto the line so it never changes retroactively (section 4.5).
- Simulated ATCUD/hash/QR (correct format, not homologated) per Decision 2,
  section 4.4, pending the real AGT signature key.

Each invoice belongs to an Activity (business line / point of sale within
the company - e.g. Padaria, Bar, Hotel - see discussion on multi-activity
companies). The Activity determines the invoice series and number padding;
both are snapshotted onto the Invoice at creation time so past documents
never reformat retroactively if the Activity's settings change later.

business_date and payments are optional - when called from the POS/Caixa
flow (see cash_session_service), business_date comes from the active
CashSession (not today's real date, so a session spanning midnight stays
on the day it opened - see CashSession model docstring) and payments
records how the sale was settled (possibly split across several methods).
Called directly by a GESTOR outside a cash session, both stay unset -
business_date defaults to today, no Payment rows are created.
"""
import hashlib
import uuid
from datetime import date, datetime

from sqlalchemy import select, func, extract, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.document_rules import DocumentRulesNotFoundError, get_document_rules, rules_from_row
from app.core.tax_exemptions import TAX_EXEMPTION_REASONS
from app.models.vat_code import VatCode
from app.models.invoice import Invoice, InvoiceStatus, InvoiceType, DocumentLifecycleStatus, CreditNoteReason
from app.models.cash_session import CashSession
from app.models.invoice_line import InvoiceLine
from app.models.product import Product
from app.models.service import Service
from app.models.withholding_tax import WithholdingTax
from app.models.customer import LegalPersonType
from app.models.vat import VAT
from app.models.customer import Customer
from app.models.activity import Activity
from app.models.payment import Payment
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.company import Company
from app.models.document_type import DocumentType
from app.services.fiscal_period_service import ensure_period_open, PeriodClosedError
from app.services.stock_service import deduct_stock_for_sale, InsufficientStockError, return_stock_for_credit_note
from app.models.stock_movement import MovementType, StockMovement
from app.services.document_series_service import get_or_create_current_series, get_next_number, SeriesNotFoundError
from app.workers.agt_worker import submit_invoice_to_agt

# Maps the (legacy) InvoiceType enum to the platform DocumentType catalog code -
# see decision on integrating DocumentSeries into invoicing.
INVOICE_TYPE_TO_DOC_CODE = {
    "FACTURA": "FT",
    "FACTURA_RECIBO": "FR",
    "NOTA_CREDITO": "NC",
    "NOTA_DEBITO": "ND",
}


class DocumentTypeNotConfiguredError(Exception):
    """Raised when the platform DocumentType catalog is missing the code this invoice_type maps to."""
    pass


class SeriesNotConfiguredError(Exception):
    """Raised when no active DocumentSeries exists for this document type/year and none can be auto-created."""
    pass



class ProductNotFoundError(Exception):
    pass


class CustomerNotFoundError(Exception):
    pass


class InvoiceNotFoundError(Exception):
    pass


class ActivityNotFoundError(Exception):
    pass


class EmptyInvoiceError(Exception):
    pass


class StockUnavailableError(Exception):
    """Raised when a line item cannot be fulfilled due to insufficient stock."""
    pass


class CashPointRequiredError(Exception):
    """A cash collection from the invoicing screen needs an explicitly chosen cash point with an open session."""


class RefundNotAllowedError(Exception):
    """The money refund asked with a credit note is not possible (amount, method, cash point) - nothing is issued."""


class PaymentAmountMismatchError(Exception):
    """Raised when the sum of the given payment lines does not equal the invoice total."""


class ReferenceInvoiceNotFoundError(Exception):
    pass


class ReferenceInvoiceTypeNotEligibleError(Exception):
    """AGT rule: a Nota de Credito can only reference a Factura, Factura/Recibo or Autofactura."""
    pass


class ReferenceInvoiceAlreadyCancelledError(Exception):
    pass


class CreditNoteExceedsOriginalError(Exception):
    """AGT rule: the credit note total/quantities cannot exceed the original invoice's."""
    pass
    pass


def _simulate_atcud(company_id: uuid.UUID, series: str, number: int) -> str:
    """
    Simulated ATCUD in the correct format (validation-code-sequence),
    clearly non-homologated - see Decision 2, section 4.4.
    """
    return f"SIMUL-{series}{number:06d}"


def _simulate_hash(company_id: uuid.UUID, series: str, number: int, total: float, business_date: date) -> str:
    """Simulated invoice hash - correct shape, not a real AGT-issued signature."""
    raw = f"{company_id}|{series}|{number}|{total}|{business_date.isoformat()}"
    return "SIMUL-" + hashlib.sha256(raw.encode()).hexdigest()[:40]


def _simulate_qr_payload(company_id: uuid.UUID, series: str, number: int, total: float, atcud: str) -> str:
    """Simulated QR code payload - correct field structure, non-homologated."""
    return f"A:SIMULATED*B:{company_id}*C:{series}/{number}*D:{total}*E:{atcud}"


async def _exemption_code_for(db: AsyncSession, article, vat_rate: float) -> str | None:
    """Code of the exemption motive of a 0% article (M04, M11...), copied on the line like vat_rate_snapshot - the
    SAF-T needs it on every exempt line. Only official codes are kept: anything else (e.g. the catalog's "NA")
    cannot be exported."""
    if vat_rate != 0 or article.exemption_reason_id is None:
        return None
    vat_code = (await db.execute(select(VatCode).where(VatCode.id == article.exemption_reason_id))).scalar_one_or_none()
    if vat_code is None or vat_code.code not in TAX_EXEMPTION_REASONS:
        return None
    return vat_code.code


async def create_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    activity_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    invoice_type: str,
    lines_input: list[dict],
    business_date: date | None = None,
    cash_session_id: uuid.UUID | None = None,
    payments: list[dict] | None = None,
    payment_term_id: uuid.UUID | None = None,
    payment_method_id: uuid.UUID | None = None,
    bank_account_id: uuid.UUID | None = None,
    due_date: date | None = None,
    amount_received: float | None = None,
    payment_date: date | None = None,
    observations: str | None = None,
    discount_global_percent: float = 0,
    document_reference: str | None = None,
    cash_pos_id: uuid.UUID | None = None,
    require_cash_point: bool = False,
    enforce_document_rules: bool = False,
) -> Invoice:
    """
    Creates an invoice with its lines, under the given Activity (which
    determines the invoice series and number padding).
    lines_input: list of {"product_id": UUID, "quantity": float}
    payments (optional): list of {"payment_method_id": UUID, "amount": float} -
    if given, must sum to exactly the invoice total (see PaymentAmountMismatchError).
    payment_method_id here refers to PaymentMethodCatalog (the 12 official AGT codes),
    same catalog as the invoice-level payment_method_id parameter below - not to be
    confused with each other: this one is per split-payment line (real cash received),
    the other is the invoice's single predicted payment method (FT, no real cash yet).
    """
    business_date = business_date or date.today()

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()
    if business_date > date.today() and not company.allows_future_sale_date:
        raise EmptyInvoiceError("Nao e permitido faturar com data futura - active essa opcao em Empresa, se necessario")

    activity_result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id, Activity.is_active == True)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada ou inativa")

    await ensure_period_open(db, company_id, business_date)

    if not lines_input:
        raise EmptyInvoiceError("A fatura deve ter pelo menos uma linha")

    customer = None
    if customer_id is not None:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.company_id == company_id)
        )
        customer = customer_result.scalar_one_or_none()
        if customer is None:
            raise CustomerNotFoundError("Cliente nao encontrado")

    doc_code = INVOICE_TYPE_TO_DOC_CODE.get(invoice_type)
    if doc_code is None:
        raise DocumentTypeNotConfiguredError(f"Tipo de fatura '{invoice_type}' nao mapeado a um tipo de documento")

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.code == doc_code))
    doc_type = doc_type_result.scalar_one_or_none()
    if doc_type is None:
        raise DocumentTypeNotConfiguredError(f"Tipo de documento '{doc_code}' nao existe no catalogo da plataforma")
    rules = rules_from_row(doc_type)

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()

    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise SeriesNotConfiguredError(str(e))

    if not series_row.is_active:
        raise SeriesNotConfiguredError(f"A serie {series_row.series_code} para {doc_code} esta inativa")

    series = series_row.series_code
    document_type_id = doc_type.id
    number_digits = activity.number_digits

    # Next sequential number for this series (never reused) - see DocumentSeries.current_number.
    next_number = await get_next_number(db, series_row)

    subtotal_total = 0.0
    vat_total = 0.0
    line_objects = []

    retention_total = 0.0
    customer_is_juridica = customer is not None and customer.legal_person_type == LegalPersonType.JURIDICA
    for line_input in lines_input:
        product_id = line_input.get("product_id")
        service_id = line_input.get("service_id")
        quantity = float(line_input["quantity"])

        if service_id:
            service_result = await db.execute(
                select(Service).where(Service.id == service_id, Service.company_id == company_id, Service.is_active == True)
            )
            service = service_result.scalar_one_or_none()
            if service is None:
                raise ProductNotFoundError("Servico nao encontrado ou inativo")
            vat_result = await db.execute(select(VAT).where(VAT.id == service.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(service.price or 0)
            item_name = service.name
            line_product_id = None
            line_service_id = service.id
            line_retention_pct = 0.0
            line_retention_name = None
            line_retention_type = None
            line_exemption_code = await _exemption_code_for(db, service, vat_rate)
            # AGT rule (Ulemo 8.8): withholding is exclusive to Service lines, requires the
            # article's own withholding_tax_id to be set ("Sujeito"), and only applies when
            # the customer is pessoa coletiva - never computed for Products or for a
            # counter sale with no customer.
            if service.withholding_tax_id and customer_is_juridica:
                wh_result = await db.execute(select(WithholdingTax).where(WithholdingTax.id == service.withholding_tax_id))
                wh = wh_result.scalar_one_or_none()
                if wh and float(wh.rate) > 0:
                    line_retention_pct = float(wh.rate)
                    line_retention_name = wh.name
                    line_retention_type = wh.tax_type
        else:
            product_result = await db.execute(
                select(Product).where(Product.id == product_id, Product.company_id == company_id, Product.is_active == True)
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                raise ProductNotFoundError("Produto nao encontrado ou inativo")
            if product.is_raw_material:
                # Raw materials are only ever consumed by production - and carry no VAT rate.
                raise ProductNotFoundError("Materia-prima nao pode ser vendida ou faturada")
            vat_result = await db.execute(select(VAT).where(VAT.id == product.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(product.price)
            item_name = product.name
            line_product_id = product.id
            line_service_id = None
            line_retention_pct = 0.0
            line_retention_name = None
            line_retention_type = None
            line_exemption_code = await _exemption_code_for(db, product, vat_rate)

        discount_percent = float(line_input.get("discount_percent", 0) or 0)
        gross_subtotal = round(quantity * unit_price, 2)
        line_discount = round(gross_subtotal * (discount_percent / 100), 2)
        line_subtotal = round(gross_subtotal - line_discount, 2)
        line_vat = round(line_subtotal * (vat_rate / 100), 2)
        line_total = round(line_subtotal + line_vat, 2)
        line_retention = round(line_subtotal * (line_retention_pct / 100), 2)

        subtotal_total += line_subtotal
        vat_total += line_vat
        retention_total += line_retention

        line_objects.append(InvoiceLine(
            product_id=line_product_id,
            service_id=line_service_id,
            product_name_snapshot=item_name,
            quantity=quantity,
            unit_price=unit_price,
            discount_percent=discount_percent,
            vat_rate_snapshot=vat_rate,
            line_subtotal=line_subtotal,
            line_vat=line_vat,
            line_total=line_total,
            retention_name_snapshot=line_retention_name if line_retention > 0 else None,
            retention_rate=line_retention_pct if line_retention > 0 else None,
            retention_amount=line_retention if line_retention > 0 else None,
            retention_type=line_retention_type if line_retention > 0 else None,
            exemption_code=line_exemption_code,
        ))

    subtotal_total = round(subtotal_total, 2)
    vat_total = round(vat_total, 2)
    retention_total = round(retention_total, 2)
    global_discount_amount = round((subtotal_total + vat_total) * (float(discount_global_percent) / 100), 2)
    grand_total = round(subtotal_total + vat_total - global_discount_amount, 2)

    # An empty payments list on a FACTURA_RECIBO (real cash-in-hand sale) means the
    # company has no payment methods marked available_at_pos for this POS (see
    # CompanyPaymentMethodPreference) - the Caixa screen lets the sale proceed rather
    # than blocking the cashier, but the cash balance must still reflect the money that
    # actually changed hands. Default the whole total to Numerario (NU) in that case -
    # see the "3000 Kz balance didn't move after a paid sale" bug discussion. FACTURA
    # (due later, no cash yet) and PRO_FORMA (not a real sale) are left alone: no
    # payments is the correct, honest state for those.
    # What the customer actually pays: the withholding is kept by the customer (and paid by him to the AGT).
    cash_due_total = round(grand_total - retention_total, 2)
    if not payments and rules.paid_on_issue and cash_due_total > 0:
        # The method chosen on the document; Numerario (NU) when none was chosen.
        default_method_id = payment_method_id
        if default_method_id is None:
            numerario_result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.code == "NU"))
            numerario = numerario_result.scalar_one_or_none()
            default_method_id = numerario.id if numerario is not None else None
        if default_method_id is not None:
            payments = [{"payment_method_id": default_method_id, "amount": cash_due_total}]

    # Only reconcile when payments were actually supplied - see the auto-default above
    # for why an empty list is sometimes filled in before reaching this point.
    if payments:
        payments_sum = round(sum(float(p["amount"]) for p in payments), 2)
        if abs(payments_sum - cash_due_total) > 0.01:
            raise PaymentAmountMismatchError(
                f"A soma dos pagamentos ({payments_sum}) nao corresponde ao montante a pagar ({cash_due_total})"
            )

    # Amount received on the document. A Fatura/Recibo is paid in full when issued: any other amount is refused.
    # A document not paid on issue (a Fatura) that records an amount received - a deposit or the whole payment - gets
    # its payment too, so the money exists in the payments (cash, reports) as a receipt would have created it.
    if amount_received:
        if amount_received > cash_due_total + 0.01:
            raise PaymentAmountMismatchError(
                f"O valor recebido ({amount_received}) excede o montante a pagar ({cash_due_total})"
            )
        if rules.paid_on_issue:
            if abs(amount_received - cash_due_total) > 0.01:
                raise PaymentAmountMismatchError(
                    "A Fatura/Recibo e paga na totalidade: para um pagamento parcial, emita uma Fatura e depois um Recibo"
                )
        elif not payments:
            deposit_method_id = payment_method_id
            if deposit_method_id is None:
                deposit_method_id = (await db.execute(
                    select(PaymentMethodCatalog.id).where(PaymentMethodCatalog.code == "NU")
                )).scalar_one_or_none()
            if deposit_method_id is not None:
                payments = [{"payment_method_id": deposit_method_id, "amount": amount_received}]

    # Payment term. A document paid on issue is always "Pronto pagamento" (the 0-day term), due on its own date - for
    # every caller. From the invoicing screen (enforce_document_rules) a mandatory term (company preference, else the
    # platform catalog) cannot be missing.
    if rules.paid_on_issue:
        from app.models.payment_term import PaymentTerm
        pronto_id = (await db.execute(
            select(PaymentTerm.id).where(
                PaymentTerm.days == 0, PaymentTerm.fixed_days.is_(False), PaymentTerm.is_active.is_(True),
            ).order_by(PaymentTerm.created_at)
        )).scalars().first()
        payment_term_id = pronto_id or payment_term_id
        due_date = business_date
    elif enforce_document_rules and not payment_term_id:
        from app.services.company_document_type_service import effective_requires_payment_term
        if (await effective_requires_payment_term(db, company_id)).get(rules.code):
            raise EmptyInvoiceError("A condicao de pagamento e obrigatoria para este tipo de documento")

    # Cash collected here goes into an explicitly chosen cash point (see _cash_point_session).
    cash_session_id = await _cash_point_session(
        db, company_id, cash_pos_id, cash_session_id, [p["payment_method_id"] for p in (payments or [])], require_cash_point,
    )

    atcud = _simulate_atcud(company_id, series, next_number)
    invoice_hash = _simulate_hash(company_id, series, next_number, grand_total, business_date)
    qr_code_data = _simulate_qr_payload(company_id, series, next_number, grand_total, atcud)

    invoice = Invoice(
        company_id=company_id,
        activity_id=activity_id,
        customer_id=customer_id,
        cash_session_id=cash_session_id,
        invoice_type=InvoiceType(invoice_type),
        document_type_id=document_type_id,
        payment_term_id=payment_term_id,
        payment_method_id=payment_method_id,
        bank_account_id=bank_account_id,
        due_date=due_date,
        amount_received=amount_received,
        payment_date=payment_date,
        observations=observations,
        document_reference=document_reference,
        discount_global_percent=discount_global_percent,
        retention_total=retention_total,
        issuance_mode=company.issuance_mode,
        series=series,
        number=next_number,
        number_digits=number_digits,
        business_date=business_date,
        subtotal=subtotal_total,
        vat_total=vat_total,
        total=grand_total,
        status=InvoiceStatus.PENDENTE,
        atcud=atcud,
        invoice_hash=invoice_hash,
        qr_code_data=qr_code_data,
    )
    db.add(invoice)
    await db.flush()

    for line in line_objects:
        line.invoice_id = invoice.id
        db.add(line)

    if payments is not None:
        for p in payments:
            db.add(Payment(
                company_id=company_id, invoice_id=invoice.id,
                payment_method_id=p["payment_method_id"], amount=float(p["amount"]),
            ))

    # Deduct stock within the SAME transaction as the invoice - if any line
    # cannot be fulfilled, the whole invoice (and its lines) rolls back
    # together, never leaving a partial sale or a partial stock deduction.
    # SAF-T XSD requires the space: "{DocType} {series_code}/{number}".
    invoice_reference = f"{doc_code} {series}/{next_number}"
    try:
        for line_input in (lines_input if rules.deducts_stock else []):
            # Services have no physical inventory - never deduct stock for them (either a
            # true Service line, or a legacy Product row typed as SERVICO).
            if line_input.get("service_id"):
                continue
            await deduct_stock_for_sale(
                db,
                company_id=company_id,
                warehouse_id=activity.warehouse_id,
                product_id=line_input["product_id"],
                quantity=float(line_input["quantity"]),
                reference=invoice_reference,
            )
    except InsufficientStockError as e:
        await db.rollback()
        raise StockUnavailableError(str(e))

    await db.commit()
    await db.refresh(invoice)

    # Trigger AGT submission asynchronously - section 4.2 requires submission
    # within 30s of creation, via a Celery task fired immediately.
    if rules.sent_to_agt:
        submit_invoice_to_agt.delay(str(invoice.id))

    return invoice


def _credit_line_key(line) -> tuple:
    """Identifies "the same kind of line" between an invoice and its credit notes. A credit note line keeps no
    link to the original line, but it copies its product/service, unit price, discount and VAT rate exactly."""
    return (
        str(line.product_id), str(line.service_id),
        round(float(line.unit_price), 2), round(float(line.discount_percent or 0), 2),
        round(float(line.vat_rate_snapshot), 2),
    )


async def attach_amount_due(db: AsyncSession, invoices: list[Invoice]) -> None:
    """Attaches, like amount_paid, what is really still owed on each document (amount_due) and the net value of the
    credit notes issued against it (amount_credited) - the one place the balance of a document is computed, for the
    Faturas list and detail, the Caixa documents and the receipt cap.

    amount_due = (total - withholding) - credit notes (net of their withholding) - (collected - refunded), never below
    0, and only for the types that take a receipt (the others are settled when issued, or owe nothing). Collected is
    the document's own payments (deposit on a Fatura) plus those of its receipts; refunded is what its credit notes
    gave back (their payments are negative)."""
    from sqlalchemy import func
    from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE

    for inv in invoices:
        inv.amount_due = 0.0
        inv.amount_credited = 0.0
    if not invoices:
        return
    ids = [inv.id for inv in invoices]

    credited: dict = {}
    note_owner: dict = {}
    for note_id, ref_id, total, retention in (await db.execute(
        select(Invoice.id, Invoice.reference_invoice_id, Invoice.total, Invoice.retention_total).where(
            Invoice.reference_invoice_id.in_(ids), Invoice.invoice_type == InvoiceType.NOTA_CREDITO,
        )
    )).all():
        credited[ref_id] = credited.get(ref_id, 0.0) + float(total) - float(retention or 0)
        note_owner[note_id] = ref_id

    payment_owner = {inv_id: inv_id for inv_id in ids}
    for receipt_id, ref_id in (await db.execute(
        select(Invoice.id, Invoice.reference_invoice_id).where(
            Invoice.reference_invoice_id.in_(ids), Invoice.invoice_type == InvoiceType.RECIBO,
        )
    )).all():
        payment_owner[receipt_id] = ref_id

    collected: dict = {}
    refunded: dict = {}
    for paid_id, amount in (await db.execute(
        select(Payment.invoice_id, func.sum(Payment.amount))
        .where(Payment.invoice_id.in_(list(payment_owner) + list(note_owner)))
        .group_by(Payment.invoice_id)
    )).all():
        if paid_id in note_owner:
            refunded[note_owner[paid_id]] = refunded.get(note_owner[paid_id], 0.0) - float(amount)
        else:
            collected[payment_owner[paid_id]] = collected.get(payment_owner[paid_id], 0.0) + float(amount)

    accepts_receipt = dict((await db.execute(select(DocumentType.code, DocumentType.accepts_receipt))).all())
    for inv in invoices:
        inv.amount_credited = round(credited.get(inv.id, 0.0), 2)
        type_value = getattr(inv.invoice_type, "value", inv.invoice_type)
        if not accepts_receipt.get(DOC_CODE_BY_INVOICE_TYPE.get(type_value, type_value)):
            continue
        due = (
            float(inv.total) - float(inv.retention_total or 0) - inv.amount_credited
            - (collected.get(inv.id, 0.0) - refunded.get(inv.id, 0.0))
        )
        inv.amount_due = round(max(due, 0.0), 2)


async def _previous_credit_notes(db: AsyncSession, reference_invoice: Invoice) -> list[Invoice]:
    """The credit notes already issued against an invoice."""
    return list((await db.execute(
        select(Invoice).where(
            Invoice.reference_invoice_id == reference_invoice.id, Invoice.invoice_type == InvoiceType.NOTA_CREDITO,
        )
    )).scalars().all())


async def _remaining_to_credit_by_key(
    db: AsyncSession, ref_lines: list[InvoiceLine], previous_notes: list[Invoice],
) -> dict[tuple, float]:
    """Quantity still creditable per kind of line (_credit_line_key): the original quantities minus what earlier credit
    notes credited - the one place the cumulative quantity cap is computed, for create_credit_note and the NC screen."""
    remaining: dict[tuple, float] = {}
    for l in ref_lines:
        remaining[_credit_line_key(l)] = remaining.get(_credit_line_key(l), 0.0) + float(l.quantity)
    if previous_notes:
        previous_lines = (await db.execute(
            select(InvoiceLine).where(InvoiceLine.invoice_id.in_([n.id for n in previous_notes]))
        )).scalars().all()
        for l in previous_lines:
            key = _credit_line_key(l)
            if key in remaining:
                remaining[key] -= float(l.quantity)
    return remaining


async def _credit_note_refund_figures(
    db: AsyncSession, reference_invoice: Invoice, previous_notes: list[Invoice],
) -> tuple[float, float, float]:
    """(collected, refunded, due) on an invoice - the one place the refund cap is computed, for create_credit_note and
    for the NC screen: what the customer really paid (the invoice's own payments - Fatura/Recibo, deposit on a Fatura -
    plus those of the receipts that settle it), what earlier credit notes already gave back (their payments are
    negative) and what is still owed once the earlier credit notes are deducted."""
    from sqlalchemy import func, or_

    receipt_ids = select(Invoice.id).where(
        Invoice.reference_invoice_id == reference_invoice.id, Invoice.invoice_type == InvoiceType.RECIBO,
    )
    collected = float((await db.execute(
        select(func.coalesce(func.sum(Payment.amount), 0)).where(
            or_(Payment.invoice_id == reference_invoice.id, Payment.invoice_id.in_(receipt_ids))
        )
    )).scalar_one())
    refunded = 0.0
    if previous_notes:
        refunded = -float((await db.execute(
            select(func.coalesce(func.sum(Payment.amount), 0)).where(
                Payment.invoice_id.in_([n.id for n in previous_notes])
            )
        )).scalar_one())
    due = (
        float(reference_invoice.total) - float(reference_invoice.retention_total or 0)
        - sum(float(n.total) - float(n.retention_total or 0) for n in previous_notes)
    )
    return round(collected, 2), round(refunded, 2), round(due, 2)


async def list_open_cash_points(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """The cash points that can take or give back cash right now (an open session), with the cash they hold."""
    from app.models.point_of_sale import PointOfSale
    from app.services.cash_session_service import get_open_session, get_current_expected_cash_balance

    cash_points = []
    for pos in (await db.execute(
        select(PointOfSale).where(PointOfSale.company_id == company_id).order_by(PointOfSale.name)
    )).scalars().all():
        session = await get_open_session(db, company_id, pos.id)
        if session is None:
            continue
        available = await get_current_expected_cash_balance(db, company_id, pos.id, session)
        cash_points.append({"pos_id": str(pos.id), "name": pos.name, "available_cash": round(available, 2)})
    return cash_points


async def _cash_point_session(
    db: AsyncSession,
    company_id: uuid.UUID,
    cash_pos_id: uuid.UUID | None,
    cash_session_id: uuid.UUID | None,
    method_ids: list,
    require_cash_point: bool,
) -> uuid.UUID | None:
    """The cash session a collection belongs to. An explicitly chosen cash point (cash_pos_id) must belong to the
    company and have an open session - resolved here, never trusted from the screen. From the invoicing screen
    (require_cash_point) cash may not be collected without one. Callers that hold their own session (the POS, hotel,
    open accounts) pass it as cash_session_id and keep it."""
    from sqlalchemy import func
    from app.models.point_of_sale import PointOfSale
    from app.services.cash_session_service import get_open_session

    if cash_pos_id is not None:
        pos = (await db.execute(
            select(PointOfSale).where(PointOfSale.id == cash_pos_id, PointOfSale.company_id == company_id)
        )).scalar_one_or_none()
        if pos is None:
            raise CashPointRequiredError("Caixa nao encontrada")
        session = await get_open_session(db, company_id, pos.id)
        if session is None:
            raise CashPointRequiredError(f"A caixa {pos.name} nao tem sessao aberta - abra a caixa antes de receber")
        return session.id
    ids = [uuid.UUID(str(m)) for m in method_ids if m]
    if require_cash_point and ids:
        cash_count = (await db.execute(
            select(func.count(PaymentMethodCatalog.id)).where(
                PaymentMethodCatalog.id.in_(ids), PaymentMethodCatalog.is_cash.is_(True),
            )
        )).scalar_one()
        if cash_count:
            raise CashPointRequiredError("Selecione a caixa onde entra o numerario")
    return cash_session_id


async def get_credit_note_info(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID) -> dict:
    """What the NC screen needs: what can still be credited on each line, the refund figures of the invoice and the
    cash points that can pay cash out right now (an open session), with the cash they hold."""
    reference_invoice = (await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == company_id)
    )).scalar_one_or_none()
    if reference_invoice is None:
        raise ReferenceInvoiceNotFoundError("Fatura de referencia nao encontrada")
    previous_notes = await _previous_credit_notes(db, reference_invoice)
    collected, refunded, due = await _credit_note_refund_figures(db, reference_invoice, previous_notes)

    # Per line, what can still be credited: the pool of a kind of line is handed out in line order, so the screen never
    # proposes more than create_credit_note accepts.
    ref_lines = list((await db.execute(
        select(InvoiceLine).where(InvoiceLine.invoice_id == reference_invoice.id)
        .order_by(InvoiceLine.created_at, InvoiceLine.id)
    )).scalars().all())
    pool = await _remaining_to_credit_by_key(db, ref_lines, previous_notes)
    remaining_by_line: dict[str, float] = {}
    for l in ref_lines:
        key = _credit_line_key(l)
        share = round(max(min(float(l.quantity), pool[key]), 0.0), 3)
        pool[key] -= share
        remaining_by_line[str(l.id)] = share

    cash_points = await list_open_cash_points(db, company_id)

    return {
        "remaining_by_line": remaining_by_line,
        "collected": collected, "refunded": refunded, "due": due, "cash_points": cash_points,
    }


async def create_credit_note(
    db: AsyncSession,
    company_id: uuid.UUID,
    activity_id: uuid.UUID,
    reference_invoice_id: uuid.UUID,
    credit_note_reason: str,
    credit_note_cause: str,
    lines_input: list[dict],
    business_date: date | None = None,
    restock: bool = False,
    refunds: list[dict] | None = None,
    refund_pos_id: uuid.UUID | None = None,
) -> Invoice:
    """
    Creates a Nota de Credito (NC) against an already-issued Factura/Factura-Recibo,
    then updates that original invoice's document_status accordingly. See Video 5 and
    the Ulemo NC endpoint rules:
    - lines_input: list of {"invoice_line_id": UUID, "quantity": float} - quantities are
      taken from the ORIGINAL invoice's own lines (same product, price, VAT rate), never
      re-priced against current catalog prices, and can be less than the original quantity
      (partial return).
    - credit_note_reason: "ANL" (anulacao) or "RTF" (rectificacao).
    - No stock moves for a credit note unless restock=True: the credited product lines go back to the
      warehouse the sale took them from (the ORIGINAL invoice's activity), and only when the credited
      document type deducts stock. It is an explicit choice of the caller - the rectification of a price
      brings nothing back. When asked for but impossible, the credit note is refused rather than silently
      issued without the return.
    - The caps are cumulative: quantities and value already credited by earlier credit notes on the same
      invoice count against the original.
    - No money is given back unless refunds are given (method + amount, as at collection): only an overpayment
      can be refunded, cash needs an explicitly chosen cash point with an open session and enough cash, and the
      refund is recorded as negative payments on the credit note. The credit note belongs to that cash point's
      session only when one was chosen - never to the issuer's own session implicitly.
    """
    business_date = business_date or date.today()

    activity_result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id, Activity.is_active == True)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada ou inativa")

    await ensure_period_open(db, company_id, business_date)

    if not lines_input:
        raise EmptyInvoiceError("A nota de credito deve ter pelo menos uma linha")

    ref_result = await db.execute(
        select(Invoice).where(Invoice.id == reference_invoice_id, Invoice.company_id == company_id)
    )
    reference_invoice = ref_result.scalar_one_or_none()
    if reference_invoice is None:
        raise ReferenceInvoiceNotFoundError("Fatura de referencia nao encontrada")

    reference_rules = await get_document_rules(db, reference_invoice.invoice_type)
    if not reference_rules.accepts_credit_note:
        raise ReferenceInvoiceTypeNotEligibleError(
            "A nota de credito so pode ser emitida para Factura ou Factura/Recibo"
        )

    if reference_invoice.document_status == DocumentLifecycleStatus.ANULADO:
        raise ReferenceInvoiceAlreadyCancelledError("A fatura de referencia ja foi anulada")

    # A credit note corrects a document that already exists: it cannot be dated before it (possible only when the
    # original was issued with a future date, allows_future_sale_date).
    if business_date < reference_invoice.business_date:
        raise EmptyInvoiceError(
            "A nota de credito nao pode ter data anterior a da fatura de referencia "
            f"({reference_invoice.business_date.strftime('%d/%m/%Y')})"
        )

    ref_lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == reference_invoice.id))
    ref_lines_by_id = {str(l.id): l for l in ref_lines_result.scalars().all()}

    # Caps are cumulative: what earlier credit notes on this invoice already credited counts against the original.
    previous_notes = await _previous_credit_notes(db, reference_invoice)
    previous_total = round(sum(float(n.total) for n in previous_notes), 2)
    remaining_by_key = await _remaining_to_credit_by_key(db, list(ref_lines_by_id.values()), previous_notes)

    subtotal_total = 0.0
    vat_total = 0.0
    retention_total = 0.0
    line_objects = []
    restock_candidates = []

    for line_input in lines_input:
        ref_line = ref_lines_by_id.get(str(line_input["invoice_line_id"]))
        if ref_line is None:
            raise ReferenceInvoiceNotFoundError("Linha da fatura de referencia nao encontrada")

        quantity = float(line_input["quantity"])
        if quantity > float(ref_line.quantity):
            raise CreditNoteExceedsOriginalError(
                f"Quantidade a creditar ({quantity}) excede a quantidade original ({ref_line.quantity})"
            )
        line_key = _credit_line_key(ref_line)
        if quantity > remaining_by_key[line_key] + 0.0005:
            raise CreditNoteExceedsOriginalError(
                f"Quantidade a creditar ({quantity}) excede a quantidade ainda por creditar de "
                f"{ref_line.product_name_snapshot} ({max(remaining_by_key[line_key], 0):g})"
            )
        remaining_by_key[line_key] -= quantity
        # Mirrors the sale: only product lines, never a service line, moved stock.
        if ref_line.product_id and not ref_line.service_id:
            restock_candidates.append((ref_line.product_id, quantity))

        unit_price = float(ref_line.unit_price)
        vat_rate = float(ref_line.vat_rate_snapshot)
        # The credited amount follows the ORIGINAL line (its line discount included), pro rata to the
        # quantity credited: re-pricing quantity x unit_price ignored the discount and could credit more
        # than was invoiced.
        line_subtotal = round(float(ref_line.line_subtotal) * quantity / float(ref_line.quantity), 2)
        line_vat = round(line_subtotal * (vat_rate / 100), 2)
        line_total = round(line_subtotal + line_vat, 2)
        # Withholding follows the rate the original line was issued with (snapshot on the line). Lines
        # issued before the snapshot existed have none: nothing is withheld on their credit note.
        ref_retention_rate = float(ref_line.retention_rate or 0)
        line_retention = round(line_subtotal * (ref_retention_rate / 100), 2) if ref_retention_rate > 0 else 0.0

        subtotal_total += line_subtotal
        vat_total += line_vat
        retention_total += line_retention

        line_objects.append(InvoiceLine(
            product_id=ref_line.product_id,
            service_id=ref_line.service_id,
            product_name_snapshot=ref_line.product_name_snapshot,
            quantity=quantity,
            unit_price=unit_price,
            vat_rate_snapshot=vat_rate,
            line_subtotal=line_subtotal,
            line_vat=line_vat,
            line_total=line_total,
            discount_percent=ref_line.discount_percent,
            retention_name_snapshot=ref_line.retention_name_snapshot if line_retention > 0 else None,
            retention_rate=ref_line.retention_rate if line_retention > 0 else None,
            retention_amount=line_retention if line_retention > 0 else None,
            retention_type=ref_line.retention_type if line_retention > 0 else None,
            exemption_code=ref_line.exemption_code,
        ))

    # Fully credited when nothing remains to credit on any line, earlier credit notes included - judging this
    # note alone left an invoice credited in several partial notes as RECTIFICADO_PARCIAL forever.
    is_full_credit = all(remaining <= 0.0005 for remaining in remaining_by_key.values())

    subtotal_total = round(subtotal_total, 2)
    vat_total = round(vat_total, 2)
    retention_total = round(retention_total, 2)
    grand_total = round(subtotal_total + vat_total, 2)

    if previous_total + grand_total > float(reference_invoice.total) + 0.01:
        if previous_total == 0:
            raise CreditNoteExceedsOriginalError(
                f"O valor da nota de credito ({grand_total}) excede o valor da fatura original ({reference_invoice.total})"
            )
        raise CreditNoteExceedsOriginalError(
            f"O valor da nota de credito ({grand_total}) excede o valor ainda por creditar da fatura original "
            f"({round(max(float(reference_invoice.total) - previous_total, 0), 2)})"
        )

    # An explicit stock return is checked BEFORE anything is created: asked for but impossible means refused
    # (EmptyInvoiceError is already mapped to 422 by the route), never a credit note issued without the return.
    restock_warehouse_by_product: dict[str, uuid.UUID] = {}
    if restock:
        if not reference_rules.deducts_stock:
            raise EmptyInvoiceError("Este tipo de documento nao movimenta stock - nao ha nada a repor")
        if not restock_candidates:
            raise EmptyInvoiceError("Nenhuma das linhas creditadas e um produto com stock - nao ha nada a repor")
        # The goods go back where the sale really took them from: the SAIDA movements written by create_invoice
        # with the original invoice's reference ("{DocType} {series}/{number}"), not the activity's current
        # warehouse, which may have changed since the sale.
        sale_reference = (
            f"{INVOICE_TYPE_TO_DOC_CODE.get(reference_invoice.invoice_type.value, '')} "
            f"{reference_invoice.series}/{reference_invoice.number}"
        )
        sale_rows = (await db.execute(
            select(StockMovement.product_id, StockMovement.warehouse_id).where(
                StockMovement.company_id == company_id,
                StockMovement.movement_type == MovementType.SAIDA,
                StockMovement.reference == sale_reference,
            )
        )).all()
        restock_warehouse_by_product = {str(product_id): warehouse_id for product_id, warehouse_id in sale_rows}
        if any(str(product_id) not in restock_warehouse_by_product for product_id, _ in restock_candidates):
            raise EmptyInvoiceError(
                "A venda desta fatura nao tem saida de stock registada - nao e possivel repor o stock"
            )

    # Explicit money refund, checked BEFORE anything is created: the credit note and its refund exist together or not
    # at all (same rule as the stock return).
    refund_session_id = None
    refund_lines: list[tuple[uuid.UUID, float, bool]] = []
    if refunds:
        from app.models.point_of_sale import PointOfSale
        from app.services.cash_session_service import get_open_session, get_current_expected_cash_balance

        method_ids = {uuid.UUID(str(r["payment_method_id"])) for r in refunds}
        methods = {m.id: m for m in (await db.execute(
            select(PaymentMethodCatalog).where(
                PaymentMethodCatalog.id.in_(method_ids), PaymentMethodCatalog.is_active.is_(True),
            )
        )).scalars().all()}
        for r in refunds:
            method = methods.get(uuid.UUID(str(r["payment_method_id"])))
            amount = round(float(r["amount"]), 2)
            if method is None:
                raise RefundNotAllowedError("Metodo de pagamento invalido ou inativo")
            if amount <= 0:
                raise RefundNotAllowedError("O valor a devolver deve ser maior que zero")
            refund_lines.append((method.id, amount, bool(method.is_cash)))
        refund_total = round(sum(amount for _, amount, _ in refund_lines), 2)

        # Only an overpayment goes back: on a Fatura not yet settled the credit note first reduces what is owed.
        collected, refunded, due_before = await _credit_note_refund_figures(db, reference_invoice, previous_notes)
        due_after = due_before - (grand_total - retention_total)
        refundable = round(max(collected - refunded - max(due_after, 0.0), 0.0), 2)
        if refund_total > refundable + 0.01:
            raise RefundNotAllowedError(
                f"O valor a devolver ({refund_total:.2f}) excede o valor reembolsavel desta fatura ({refundable:.2f})"
            )

        cash_total = round(sum(amount for _, amount, is_cash in refund_lines if is_cash), 2)
        if refund_pos_id is None and cash_total > 0:
            raise RefundNotAllowedError("Selecione a caixa de onde sai o numerario a devolver")
        if refund_pos_id is not None:
            pos = (await db.execute(
                select(PointOfSale).where(PointOfSale.id == refund_pos_id, PointOfSale.company_id == company_id)
            )).scalar_one_or_none()
            if pos is None:
                raise RefundNotAllowedError("Caixa nao encontrada")
            refund_session = await get_open_session(db, company_id, pos.id)
            if refund_session is None:
                raise RefundNotAllowedError(f"A caixa {pos.name} nao tem sessao aberta - abra a caixa antes de devolver")
            if cash_total > 0:
                available = await get_current_expected_cash_balance(db, company_id, pos.id, refund_session)
                if cash_total > available + 0.01:
                    raise RefundNotAllowedError(
                        f"Numerario insuficiente na caixa {pos.name} (disponivel: {available:.2f})"
                    )
            refund_session_id = refund_session.id
    elif refund_pos_id is not None:
        raise RefundNotAllowedError("Foi escolhida uma caixa mas nenhum valor a devolver")

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.code == "NC"))
    doc_type = doc_type_result.scalar_one_or_none()
    if doc_type is None:
        raise DocumentTypeNotConfiguredError("Tipo de documento 'NC' nao existe no catalogo da plataforma")
    rules = rules_from_row(doc_type)

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()

    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise SeriesNotConfiguredError(str(e))

    if not series_row.is_active:
        raise SeriesNotConfiguredError(f"A serie {series_row.series_code} para NC esta inativa")

    next_number = await get_next_number(db, series_row)
    number_digits = activity.number_digits

    invoice_reference = f"NC {series_row.series_code}/{next_number}"
    atcud = _simulate_atcud(company_id, series_row.series_code, next_number)
    invoice_hash = _simulate_hash(company_id, series_row.series_code, next_number, grand_total, business_date)
    qr_code_data = _simulate_qr_payload(company_id, series_row.series_code, next_number, grand_total, atcud)

    credit_note = Invoice(
        company_id=company_id,
        activity_id=activity_id,
        customer_id=reference_invoice.customer_id,
        cash_session_id=refund_session_id,
        invoice_type=InvoiceType.NOTA_CREDITO,
        document_type_id=doc_type.id,
        series=series_row.series_code,
        number=next_number,
        number_digits=number_digits,
        business_date=business_date,
        subtotal=subtotal_total,
        vat_total=vat_total,
        total=grand_total,
        status=InvoiceStatus.PENDENTE,
        document_status=DocumentLifecycleStatus.EMITIDO,
        reference_invoice_id=reference_invoice.id,
        document_reference=f"{INVOICE_TYPE_TO_DOC_CODE.get(reference_invoice.invoice_type.value, '')} {reference_invoice.series}/{reference_invoice.number}",
        credit_note_reason=CreditNoteReason(credit_note_reason),
        credit_note_cause=credit_note_cause,
        retention_total=retention_total,
        issuance_mode=company.issuance_mode,
        atcud=atcud,
        invoice_hash=invoice_hash,
        qr_code_data=qr_code_data,
    )
    db.add(credit_note)
    await db.flush()

    for line in line_objects:
        line.invoice_id = credit_note.id
        db.add(line)

    # The refund: negative payments on the credit note - money going out, so every sum of payments (the cash point's
    # expected balance, the daily journal) counts it as such without a special case.
    for refund_method_id, refund_amount, _ in refund_lines:
        db.add(Payment(
            company_id=company_id, invoice_id=credit_note.id, payment_method_id=refund_method_id, amount=-refund_amount,
        ))

    # Explicit stock return, inside the credit note's own transaction: both exist or neither does.
    if restock:
        for restock_product_id, restock_quantity in restock_candidates:
            await return_stock_for_credit_note(
                db, company_id, restock_warehouse_by_product[str(restock_product_id)], restock_product_id,
                restock_quantity, invoice_reference,
            )

    # Update the original invoice's fiscal lifecycle - see Video 5.
    if is_full_credit:
        reference_invoice.document_status = (
            DocumentLifecycleStatus.ANULADO if CreditNoteReason(credit_note_reason) == CreditNoteReason.ANL
            else DocumentLifecycleStatus.RECTIFICADO
        )
    else:
        reference_invoice.document_status = DocumentLifecycleStatus.RECTIFICADO_PARCIAL

    await db.commit()
    await db.refresh(credit_note)

    if rules.sent_to_agt:
        submit_invoice_to_agt.delay(str(credit_note.id))

    return credit_note


async def create_debit_note(
    db: AsyncSession,
    company_id: uuid.UUID,
    activity_id: uuid.UUID,
    reference_invoice_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    lines_input: list[dict],
    business_date: date | None = None,
    document_reference: str | None = None,
    observations: str | None = None,
    cash_session_id: uuid.UUID | None = None,
) -> Invoice:
    """
    Creates a Nota de Debito (ND) referencing an already-issued Factura/Factura-Recibo/
    Autofactura, for charging an additional amount not covered by the original (e.g. an
    omitted item, a price correction upward) - see Video 5 decision. Unlike a Nota de
    Credito, an ND's lines are freely specified (not limited to the original's own lines
    or quantities), and it does NOT alter the original invoice's document_status - it adds
    to what is owed rather than crediting/cancelling what was already billed.
    """
    business_date = business_date or date.today()

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()
    if business_date > date.today() and not company.allows_future_sale_date:
        raise EmptyInvoiceError("Nao e permitido faturar com data futura - active essa opcao em Empresa, se necessario")

    activity_result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id, Activity.is_active == True)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada ou inativa")

    await ensure_period_open(db, company_id, business_date)

    if not lines_input:
        raise EmptyInvoiceError("A nota de debito deve ter pelo menos uma linha")

    ref_result = await db.execute(
        select(Invoice).where(Invoice.id == reference_invoice_id, Invoice.company_id == company_id)
    )
    reference_invoice = ref_result.scalar_one_or_none()
    if reference_invoice is None:
        raise ReferenceInvoiceNotFoundError("Fatura de referencia nao encontrada")

    reference_rules = await get_document_rules(db, reference_invoice.invoice_type)
    if not reference_rules.accepts_debit_note:
        raise ReferenceInvoiceTypeNotEligibleError(
            "A nota de debito so pode ser emitida para Factura ou Factura/Recibo"
        )

    if reference_invoice.document_status == DocumentLifecycleStatus.ANULADO:
        raise ReferenceInvoiceAlreadyCancelledError("A fatura de referencia ja foi anulada")

    customer = None
    if customer_id is not None:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.company_id == company_id)
        )
        customer = customer_result.scalar_one_or_none()
        if customer is None:
            raise CustomerNotFoundError("Cliente nao encontrado")

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.code == "ND"))
    doc_type = doc_type_result.scalar_one_or_none()
    if doc_type is None:
        raise DocumentTypeNotConfiguredError("Tipo de documento 'ND' nao existe no catalogo da plataforma")
    rules = rules_from_row(doc_type)

    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise SeriesNotConfiguredError(str(e))

    if not series_row.is_active:
        raise SeriesNotConfiguredError(f"A serie {series_row.series_code} para ND esta inativa")

    subtotal_total = 0.0
    vat_total = 0.0
    retention_total = 0.0
    line_objects = []
    customer_is_juridica = customer is not None and customer.legal_person_type == LegalPersonType.JURIDICA

    for line_input in lines_input:
        product_id = line_input.get("product_id")
        service_id = line_input.get("service_id")
        quantity = float(line_input["quantity"])
        line_retention_pct = 0.0
        line_retention_name = None
        line_retention_type = None

        if service_id:
            service_result = await db.execute(
                select(Service).where(Service.id == service_id, Service.company_id == company_id, Service.is_active == True)
            )
            service = service_result.scalar_one_or_none()
            if service is None:
                raise ProductNotFoundError("Servico nao encontrado ou inativo")
            vat_result = await db.execute(select(VAT).where(VAT.id == service.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(service.price or 0)
            item_name = service.name
            line_product_id = None
            line_service_id = service.id
            line_exemption_code = await _exemption_code_for(db, service, vat_rate)
            if service.withholding_tax_id and customer_is_juridica:
                wh_result = await db.execute(select(WithholdingTax).where(WithholdingTax.id == service.withholding_tax_id))
                wh = wh_result.scalar_one_or_none()
                if wh and float(wh.rate) > 0:
                    line_retention_pct = float(wh.rate)
                    line_retention_name = wh.name
                    line_retention_type = wh.tax_type
        else:
            product_result = await db.execute(
                select(Product).where(Product.id == product_id, Product.company_id == company_id, Product.is_active == True)
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                raise ProductNotFoundError("Produto nao encontrado ou inativo")
            if product.is_raw_material:
                # Raw materials are only ever consumed by production - and carry no VAT rate.
                raise ProductNotFoundError("Materia-prima nao pode ser vendida ou faturada")
            vat_result = await db.execute(select(VAT).where(VAT.id == product.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(product.price)
            item_name = product.name
            line_product_id = product.id
            line_service_id = None
            line_exemption_code = await _exemption_code_for(db, product, vat_rate)

        discount_percent = float(line_input.get("discount_percent", 0) or 0)
        gross_subtotal = round(quantity * unit_price, 2)
        line_discount = round(gross_subtotal * (discount_percent / 100), 2)
        line_subtotal = round(gross_subtotal - line_discount, 2)
        line_vat = round(line_subtotal * (vat_rate / 100), 2)
        line_total = round(line_subtotal + line_vat, 2)
        line_retention = round(line_subtotal * (line_retention_pct / 100), 2)

        subtotal_total += line_subtotal
        vat_total += line_vat
        retention_total += line_retention

        line_objects.append(InvoiceLine(
            product_id=line_product_id,
            service_id=line_service_id,
            product_name_snapshot=item_name,
            quantity=quantity,
            unit_price=unit_price,
            discount_percent=discount_percent,
            vat_rate_snapshot=vat_rate,
            line_subtotal=line_subtotal,
            line_vat=line_vat,
            line_total=line_total,
            retention_name_snapshot=line_retention_name if line_retention > 0 else None,
            retention_rate=line_retention_pct if line_retention > 0 else None,
            retention_amount=line_retention if line_retention > 0 else None,
            retention_type=line_retention_type if line_retention > 0 else None,
            exemption_code=line_exemption_code,
        ))

    subtotal_total = round(subtotal_total, 2)
    vat_total = round(vat_total, 2)
    retention_total = round(retention_total, 2)
    grand_total = round(subtotal_total + vat_total, 2)

    next_number = await get_next_number(db, series_row)
    number_digits = activity.number_digits

    atcud = _simulate_atcud(company_id, series_row.series_code, next_number)
    invoice_hash = _simulate_hash(company_id, series_row.series_code, next_number, grand_total, business_date)
    qr_code_data = _simulate_qr_payload(company_id, series_row.series_code, next_number, grand_total, atcud)

    debit_note = Invoice(
        company_id=company_id,
        activity_id=activity_id,
        customer_id=customer_id if customer_id is not None else reference_invoice.customer_id,
        cash_session_id=cash_session_id,
        invoice_type=InvoiceType.NOTA_DEBITO,
        document_type_id=doc_type.id,
        series=series_row.series_code,
        number=next_number,
        number_digits=number_digits,
        business_date=business_date,
        subtotal=subtotal_total,
        vat_total=vat_total,
        total=grand_total,
        status=InvoiceStatus.PENDENTE,
        document_status=DocumentLifecycleStatus.EMITIDO,
        reference_invoice_id=reference_invoice.id,
        document_reference=document_reference,
        observations=observations,
        retention_total=retention_total,
        issuance_mode=company.issuance_mode,
        atcud=atcud,
        invoice_hash=invoice_hash,
        qr_code_data=qr_code_data,
    )
    db.add(debit_note)
    await db.flush()

    for line in line_objects:
        line.invoice_id = debit_note.id
        db.add(line)

    await db.commit()
    await db.refresh(debit_note)

    if rules.sent_to_agt:
        submit_invoice_to_agt.delay(str(debit_note.id))

    return debit_note


class ReceiptExceedsPendingError(Exception):
    """Raised when the receipt amount exceeds the reference invoice's remaining balance."""
    pass


async def create_receipt(
    db: AsyncSession,
    company_id: uuid.UUID,
    activity_id: uuid.UUID,
    reference_invoice_id: uuid.UUID,
    amount: float,
    business_date: date | None = None,
    document_reference: str | None = None,
    observations: str | None = None,
    payment_method_id: uuid.UUID | None = None,
    cash_session_id: uuid.UUID | None = None,
    cash_pos_id: uuid.UUID | None = None,
    require_cash_point: bool = False,
    bank_account_id: uuid.UUID | None = None,
) -> Invoice:
    """
    Creates a Recibo (RC) - a standalone payment acknowledgement against an already-issued
    Factura/Factura-Recibo. Unlike NC/ND, an RC has no product/service lines - it simply
    records that `amount` was paid, and accumulates into the reference invoice's own
    amount_received/payment_date (see Ulemo RC rules: "TOTAL_RECIBO_EXCEDEU" when the
    amount exceeds the remaining balance).
    """
    business_date = business_date or date.today()

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()
    if business_date > date.today() and not company.allows_future_sale_date:
        raise EmptyInvoiceError("Nao e permitido faturar com data futura - active essa opcao em Empresa, se necessario")

    activity_result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id, Activity.is_active == True)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada ou inativa")

    await ensure_period_open(db, company_id, business_date)

    if amount is None or amount <= 0:
        raise EmptyInvoiceError("O valor do recibo deve ser maior que zero")

    ref_result = await db.execute(
        select(Invoice).where(Invoice.id == reference_invoice_id, Invoice.company_id == company_id)
    )
    reference_invoice = ref_result.scalar_one_or_none()
    if reference_invoice is None:
        raise ReferenceInvoiceNotFoundError("Fatura de referencia nao encontrada")

    reference_rules = await get_document_rules(db, reference_invoice.invoice_type)
    if not reference_rules.accepts_receipt:
        # A Fatura/Recibo is paid when it is issued: a receipt on top would collect the same money twice.
        raise ReferenceInvoiceTypeNotEligibleError(
            "O recibo so pode ser emitido para uma Factura (a Factura/Recibo ja esta paga)"
        )

    if reference_invoice.document_status == DocumentLifecycleStatus.ANULADO:
        raise ReferenceInvoiceAlreadyCancelledError("A fatura de referencia ja foi anulada")

    already_received = float(reference_invoice.amount_received or 0)
    # What is really still owed: the credit notes on the invoice (and what they refunded) count.
    await attach_amount_due(db, [reference_invoice])
    pending = reference_invoice.amount_due
    if amount > pending + 0.01:
        raise ReceiptExceedsPendingError(
            f"O valor do recibo ({amount}) excede o valor pendente da fatura ({pending})"
        )

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.code == "RC"))
    doc_type = doc_type_result.scalar_one_or_none()
    if doc_type is None:
        raise DocumentTypeNotConfiguredError("Tipo de documento 'RC' nao existe no catalogo da plataforma")
    rules = rules_from_row(doc_type)

    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise SeriesNotConfiguredError(str(e))

    if not series_row.is_active:
        raise SeriesNotConfiguredError(f"A serie {series_row.series_code} para RC esta inativa")

    next_number = await get_next_number(db, series_row)
    number_digits = activity.number_digits
    amount = round(amount, 2)

    atcud = _simulate_atcud(company_id, series_row.series_code, next_number)
    invoice_hash = _simulate_hash(company_id, series_row.series_code, next_number, amount, business_date)
    qr_code_data = _simulate_qr_payload(company_id, series_row.series_code, next_number, amount, atcud)

    # The receipt settles the invoice pro rata: `amount` is the cash received and the rest of the settled share is
    # the withholding kept by the customer. The receipt carries the settled part of the document (net, VAT, total,
    # withholding) - what the SAF-T Payments section and the AGT e-invoicing API expect - and the cash itself in
    # amount_received / Payment.
    cash_due_total = float(reference_invoice.total) - float(reference_invoice.retention_total or 0)
    settled_share = amount / cash_due_total if cash_due_total > 0 else 1.0
    receipt_total = round(float(reference_invoice.total) * settled_share, 2)
    receipt_vat = round(float(reference_invoice.vat_total) * settled_share, 2)
    receipt_net = round(receipt_total - receipt_vat, 2)
    receipt_retention = round(float(reference_invoice.retention_total or 0) * settled_share, 2)

    # How the money was paid: the method given, else the invoice's own, else Numerario (as for a Fatura/Recibo).
    method_id = payment_method_id or reference_invoice.payment_method_id
    if payment_method_id is not None:
        known = (await db.execute(select(PaymentMethodCatalog.id).where(PaymentMethodCatalog.id == payment_method_id))).scalar_one_or_none()
        if known is None:
            raise EmptyInvoiceError("Metodo de pagamento invalido")
    if method_id is None:
        method_id = (await db.execute(select(PaymentMethodCatalog.id).where(PaymentMethodCatalog.code == "NU"))).scalar_one_or_none()
    # Cash collected here goes into an explicitly chosen cash point (see _cash_point_session).
    cash_session_id = await _cash_point_session(
        db, company_id, cash_pos_id, cash_session_id, [method_id] if method_id else [], require_cash_point,
    )
    # The bank account the money lands on (a method with uses_bank_account) must be one of the company's.
    if bank_account_id is not None:
        from app.models.company_bank_account import CompanyBankAccount
        known_account = (await db.execute(
            select(CompanyBankAccount.id).where(
                CompanyBankAccount.id == bank_account_id, CompanyBankAccount.company_id == company_id,
            )
        )).scalar_one_or_none()
        if known_account is None:
            raise EmptyInvoiceError("Conta bancaria invalida")

    receipt = Invoice(
        company_id=company_id,
        activity_id=activity_id,
        customer_id=reference_invoice.customer_id,
        invoice_type=InvoiceType.RECIBO,
        document_type_id=doc_type.id,
        series=series_row.series_code,
        number=next_number,
        number_digits=number_digits,
        business_date=business_date,
        subtotal=receipt_net,
        vat_total=receipt_vat,
        total=receipt_total,
        retention_total=receipt_retention,
        cash_session_id=cash_session_id,
        bank_account_id=bank_account_id,
        status=InvoiceStatus.PENDENTE,
        document_status=DocumentLifecycleStatus.EMITIDO,
        reference_invoice_id=reference_invoice.id,
        document_reference=document_reference,
        observations=observations,
        amount_received=amount,
        payment_date=business_date,
        issuance_mode=company.issuance_mode,
        atcud=atcud,
        invoice_hash=invoice_hash,
        qr_code_data=qr_code_data,
    )
    db.add(receipt)
    await db.flush()
    if method_id is not None:
        db.add(Payment(company_id=company_id, invoice_id=receipt.id, payment_method_id=method_id, amount=amount))

    # Accumulate the payment onto the original invoice - see Estado Pagamento derivation.
    reference_invoice.amount_received = round(already_received + amount, 2)
    reference_invoice.payment_date = business_date

    await db.commit()
    await db.refresh(receipt)

    if rules.sent_to_agt:
        submit_invoice_to_agt.delay(str(receipt.id))

    return receipt


async def create_pro_forma(
    db: AsyncSession,
    company_id: uuid.UUID,
    activity_id: uuid.UUID,
    customer_id: uuid.UUID | None,
    lines_input: list[dict],
    business_date: date | None = None,
    document_reference: str | None = None,
    observations: str | None = None,
    discount_global_percent: float = 0,
) -> Invoice:
    """
    Creates a Fatura Pro-forma (FP) - a non-fiscal quote/preview document. Unlike FT/FR/NC/ND/RC:
    - Never submitted to AGT (no submit_invoice_to_agt.delay call)
    - Does not deduct stock (no real sale has happened yet)
    - atcud/hash/qr are simulated placeholders only, never meaningful for compliance
    See Video 4 spec: "FP Factura Pro-forma" in the tipo de documento list, and the SAF-T
    WorkingDocuments vs SalesInvoices distinction (is_fiscal=False on this DocumentType).
    """
    business_date = business_date or date.today()

    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one()

    activity_result = await db.execute(
        select(Activity).where(Activity.id == activity_id, Activity.company_id == company_id, Activity.is_active == True)
    )
    activity = activity_result.scalar_one_or_none()
    if activity is None:
        raise ActivityNotFoundError("Atividade nao encontrada ou inativa")

    if not lines_input:
        raise EmptyInvoiceError("A pro-forma deve ter pelo menos uma linha")

    customer = None
    if customer_id is not None:
        customer_result = await db.execute(
            select(Customer).where(Customer.id == customer_id, Customer.company_id == company_id)
        )
        customer = customer_result.scalar_one_or_none()
        if customer is None:
            raise CustomerNotFoundError("Cliente nao encontrado")

    doc_type_result = await db.execute(select(DocumentType).where(DocumentType.code == "FP"))
    doc_type = doc_type_result.scalar_one_or_none()
    if doc_type is None:
        raise DocumentTypeNotConfiguredError("Tipo de documento 'FP' nao existe no catalogo da plataforma")

    try:
        series_row = await get_or_create_current_series(db, company, doc_type.id)
    except SeriesNotFoundError as e:
        raise SeriesNotConfiguredError(str(e))

    if not series_row.is_active:
        raise SeriesNotConfiguredError(f"A serie {series_row.series_code} para FP esta inativa")

    subtotal_total = 0.0
    vat_total = 0.0
    pro_forma_retention = 0.0
    line_objects = []
    customer_is_juridica = customer is not None and customer.legal_person_type == LegalPersonType.JURIDICA

    for line_input in lines_input:
        product_id = line_input.get("product_id")
        service_id = line_input.get("service_id")
        quantity = float(line_input["quantity"])

        if service_id:
            service_result = await db.execute(
                select(Service).where(Service.id == service_id, Service.company_id == company_id, Service.is_active == True)
            )
            service = service_result.scalar_one_or_none()
            if service is None:
                raise ProductNotFoundError("Servico nao encontrado ou inativo")
            vat_result = await db.execute(select(VAT).where(VAT.id == service.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(service.price or 0)
            item_name = service.name
            line_product_id = None
            line_service_id = service.id
            line_exemption_code = await _exemption_code_for(db, service, vat_rate)
            line_retention_pct, line_retention_name, line_retention_type = 0.0, None, None
            # same rule as the invoice: a service with a withholding, sold to a pessoa coletiva
            if service.withholding_tax_id and customer_is_juridica:
                wh = (await db.execute(select(WithholdingTax).where(WithholdingTax.id == service.withholding_tax_id))).scalar_one_or_none()
                if wh and float(wh.rate) > 0:
                    line_retention_pct, line_retention_name, line_retention_type = float(wh.rate), wh.name, wh.tax_type
        else:
            product_result = await db.execute(
                select(Product).where(Product.id == product_id, Product.company_id == company_id, Product.is_active == True)
            )
            product = product_result.scalar_one_or_none()
            if product is None:
                raise ProductNotFoundError("Produto nao encontrado ou inativo")
            if product.is_raw_material:
                # Raw materials are only ever consumed by production - and carry no VAT rate.
                raise ProductNotFoundError("Materia-prima nao pode ser vendida ou faturada")
            vat_result = await db.execute(select(VAT).where(VAT.id == product.vat_id))
            vat = vat_result.scalar_one_or_none()
            vat_rate = float(vat.rate) if vat else 0.0
            unit_price = float(product.price)
            item_name = product.name
            line_product_id = product.id
            line_service_id = None
            line_exemption_code = await _exemption_code_for(db, product, vat_rate)
            line_retention_pct, line_retention_name, line_retention_type = 0.0, None, None

        discount_percent = float(line_input.get("discount_percent", 0) or 0)
        gross_subtotal = round(quantity * unit_price, 2)
        line_discount = round(gross_subtotal * (discount_percent / 100), 2)
        line_subtotal = round(gross_subtotal - line_discount, 2)
        line_vat = round(line_subtotal * (vat_rate / 100), 2)
        line_total = round(line_subtotal + line_vat, 2)
        line_retention = round(line_subtotal * (line_retention_pct / 100), 2)

        subtotal_total += line_subtotal
        vat_total += line_vat
        pro_forma_retention += line_retention

        line_objects.append(InvoiceLine(
            product_id=line_product_id,
            service_id=line_service_id,
            product_name_snapshot=item_name,
            quantity=quantity,
            unit_price=unit_price,
            discount_percent=discount_percent,
            vat_rate_snapshot=vat_rate,
            line_subtotal=line_subtotal,
            line_vat=line_vat,
            line_total=line_total,
            retention_name_snapshot=line_retention_name if line_retention > 0 else None,
            retention_rate=line_retention_pct if line_retention > 0 else None,
            retention_amount=line_retention if line_retention > 0 else None,
            retention_type=line_retention_type if line_retention > 0 else None,
            exemption_code=line_exemption_code,
        ))

    subtotal_total = round(subtotal_total, 2)
    vat_total = round(vat_total, 2)
    pro_forma_retention = round(pro_forma_retention, 2)
    gross_total = round(subtotal_total + vat_total, 2)
    global_discount_amount = round(gross_total * (discount_global_percent / 100), 2)
    grand_total = round(gross_total - global_discount_amount, 2)

    next_number = await get_next_number(db, series_row)
    number_digits = activity.number_digits

    # Simulated only - a Pro-forma has no real ATCUD/hash, it is never submitted to AGT.
    atcud = _simulate_atcud(company_id, series_row.series_code, next_number)
    invoice_hash = _simulate_hash(company_id, series_row.series_code, next_number, grand_total, business_date)
    qr_code_data = _simulate_qr_payload(company_id, series_row.series_code, next_number, grand_total, atcud)

    pro_forma = Invoice(
        company_id=company_id,
        activity_id=activity_id,
        customer_id=customer_id,
        invoice_type=InvoiceType.PRO_FORMA,
        document_type_id=doc_type.id,
        series=series_row.series_code,
        number=next_number,
        number_digits=number_digits,
        business_date=business_date,
        subtotal=subtotal_total,
        vat_total=vat_total,
        total=grand_total,
        retention_total=pro_forma_retention,
        discount_global_percent=discount_global_percent,
        status=InvoiceStatus.PENDENTE,
        document_status=DocumentLifecycleStatus.EMITIDO,
        document_reference=document_reference,
        observations=observations,
        issuance_mode=company.issuance_mode,
        atcud=atcud,
        invoice_hash=invoice_hash,
        qr_code_data=qr_code_data,
    )
    db.add(pro_forma)
    await db.flush()

    for line in line_objects:
        line.invoice_id = pro_forma.id
        db.add(line)

    await db.commit()
    await db.refresh(pro_forma)

    # Deliberately NOT calling submit_invoice_to_agt.delay() here - FP is non-fiscal.

    return pro_forma


class ProFormaNotFoundError(Exception):
    """Raised when the given id does not point to an existing Pro-forma."""
    pass


class ProFormaAlreadyConvertedError(Exception):
    """Raised when trying to convert a Pro-forma that has already been converted once."""
    pass


async def convert_pro_forma_to_invoice(
    db: AsyncSession,
    company_id: uuid.UUID,
    pro_forma_id: uuid.UUID,
    target_invoice_type: str,
    business_date: date | None = None,
    payment_term_id: uuid.UUID | None = None,
    payment_method_id: uuid.UUID | None = None,
    bank_account_id: uuid.UUID | None = None,
    due_date: date | None = None,
    cash_session_id: uuid.UUID | None = None,
    payments: list[dict] | None = None,
) -> Invoice:
    """
    Converts a Pro-forma (FP) into a real fiscal Factura/Factura-Recibo, replaying its lines
    through the normal create_invoice flow (so stock deduction, VAT, retention and AGT
    submission all behave exactly like a fresh sale) - see Kiami's "passar a FT/FR" action.
    A Pro-forma can only be converted once; converting again raises
    ProFormaAlreadyConvertedError.

    cash_session_id/payments are optional pass-throughs for the Caixa liquidation flow
    (see pos_service.checkout) - when supplied, the resulting invoice is linked to that
    session exactly like a fresh POS sale, so close_session's expected-amount calculation
    picks it up correctly. The Invoices.jsx admin conversion flow omits both and behaves
    exactly as before.
    """
    pf_result = await db.execute(
        select(Invoice).where(Invoice.id == pro_forma_id, Invoice.company_id == company_id)
    )
    pro_forma = pf_result.scalar_one_or_none()
    # The source must be a document the catalog says can be converted (a pro-forma); the target a plain invoice.
    if pro_forma is None or not (await get_document_rules(db, pro_forma.invoice_type)).convertible:
        raise ProFormaNotFoundError("Documento nao encontrado ou nao convertivel")
    try:
        target_rules = await get_document_rules(db, target_invoice_type)
    except DocumentRulesNotFoundError:
        raise ReferenceInvoiceTypeNotEligibleError("O tipo de documento de destino nao e valido para uma conversao")
    if target_rules.saft_section != "INVOICES" or target_rules.requires_origin:
        raise ReferenceInvoiceTypeNotEligibleError("O tipo de documento de destino nao e valido para uma conversao")

    if pro_forma.converted_to_invoice_id is not None:
        raise ProFormaAlreadyConvertedError("Esta pro-forma ja foi convertida numa fatura")

    lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == pro_forma.id))
    pf_lines = lines_result.scalars().all()
    lines_input = [
        {
            "product_id": line.product_id,
            "service_id": line.service_id,
            "quantity": float(line.quantity),
            "discount_percent": float(line.discount_percent or 0),
        }
        for line in pf_lines
    ]

    new_invoice = await create_invoice(
        db,
        company_id=company_id,
        activity_id=pro_forma.activity_id,
        customer_id=pro_forma.customer_id,
        invoice_type=target_invoice_type,
        lines_input=lines_input,
        business_date=business_date,
        payment_term_id=payment_term_id,
        payment_method_id=payment_method_id,
        bank_account_id=bank_account_id,
        due_date=due_date,
        observations=pro_forma.observations,
        discount_global_percent=float(pro_forma.discount_global_percent or 0),
        document_reference=f"FP {pro_forma.series}/{pro_forma.number}",
        cash_session_id=cash_session_id,
        payments=payments,
    )

    pro_forma.converted_to_invoice_id = new_invoice.id
    await db.commit()
    await db.refresh(new_invoice)

    return new_invoice


async def list_invoices(
    db: AsyncSession,
    company_id: uuid.UUID,
    year: int | None = None,
    month: int | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    limit: int = 50,
    offset: int = 0,
    invoice_type: str | None = None,
    pending_only: bool = False,
    pos_id: uuid.UUID | None = None,
) -> list[Invoice]:
    """
    Lists invoices, newest first, with optional filters (year/month OR an
    explicit date_from/date_to range - both can combine) and pagination
    (limit/offset) - see discussion on filtering + "Carregar mais".

    invoice_type filters to one InvoiceType (e.g. "PRO_FORMA"). pending_only,
    combined with invoice_type="PRO_FORMA", is the Caixa liquidation search:
    pro-formas not yet converted to a real invoice (converted_to_invoice_id
    IS NULL) - see pos_service.liquidate_pending_invoice.

    pos_id restricts real invoices (FT/FR/NC/ND/RC) to the sessions of that one POS - the CAIXA
    role only sees documents from its own cash point. Pro-formas are never restricted this way
    (they have no cash_session_id until liquidated, and any cashier can liquidate any of them -
    see point-8 discussion). The caller (route) passes pos_id only for CAIXA; None for GESTOR.
    """
    query = select(Invoice).where(Invoice.company_id == company_id)
    if year is not None:
        query = query.where(extract("year", Invoice.business_date) == year)
    if month is not None:
        query = query.where(extract("month", Invoice.business_date) == month)
    if date_from is not None:
        query = query.where(Invoice.business_date >= date_from)
    if date_to is not None:
        query = query.where(Invoice.business_date <= date_to)
    if invoice_type is not None:
        query = query.where(Invoice.invoice_type == InvoiceType(invoice_type))
    if pending_only:
        query = query.where(Invoice.converted_to_invoice_id.is_(None))
    if pos_id is not None:
        session_ids = select(CashSession.id).where(CashSession.pos_id == pos_id)
        query = query.where(or_(Invoice.invoice_type == InvoiceType.PRO_FORMA, Invoice.cash_session_id.in_(session_ids)))
    query = query.order_by(Invoice.created_at.desc()).limit(limit).offset(offset)

    result = await db.execute(query)
    invoices_list = list(result.scalars().all())

    # Attach item_count dynamically (not a real column) - InvoiceResponse picks it up via
    # from_attributes/getattr, avoiding a schema/route rewrite for this one derived field.
    if invoices_list:
        invoice_ids = [inv.id for inv in invoices_list]
        count_result = await db.execute(
            select(InvoiceLine.invoice_id, func.count(InvoiceLine.id))
            .where(InvoiceLine.invoice_id.in_(invoice_ids))
            .group_by(InvoiceLine.invoice_id)
        )
        counts_by_id = dict(count_result.all())
        for inv in invoices_list:
            inv.item_count = counts_by_id.get(inv.id, 0)

        # Attach customer_name dynamically too (not a real column, same mechanism as item_count above) -
        # the Caixa's pending pro-formas table shows it, e.g. Consumidor final or "-" for a walk-in.
        customer_ids = [inv.customer_id for inv in invoices_list if inv.customer_id]
        name_by_id = {}
        if customer_ids:
            name_result = await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids)))
            name_by_id = dict(name_result.all())
        for inv in invoices_list:
            inv.customer_name = name_by_id.get(inv.customer_id)

        # Attach amount_paid dynamically as well: the real sum of Payment rows on each document (same mechanism as
        # item_count, and as pos_documents_service does for the Caixa table). amount_received stays empty on a
        # Fatura/Recibo paid at the till, so the Faturas list needs this to show it as paid.
        paid_result = await db.execute(
            select(Payment.invoice_id, func.sum(Payment.amount))
            .where(Payment.invoice_id.in_(invoice_ids))
            .group_by(Payment.invoice_id)
        )
        paid_by_id = dict(paid_result.all())
        for inv in invoices_list:
            inv.amount_paid = float(paid_by_id.get(inv.id, 0) or 0)
        await attach_amount_due(db, invoices_list)

    return invoices_list


async def get_invoice_periods(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Returns the distinct (year, month) pairs that have at least one invoice - populates the Ano/Mes filters."""
    result = await db.execute(
        select(
            extract("year", Invoice.business_date).label("year"),
            extract("month", Invoice.business_date).label("month"),
        )
        .where(Invoice.company_id == company_id)
        .distinct()
        .order_by(extract("year", Invoice.business_date).desc(), extract("month", Invoice.business_date).desc())
    )
    return [{"year": int(row.year), "month": int(row.month)} for row in result.all()]


async def get_invoice_with_lines(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID):
    result = await db.execute(
        select(Invoice).where(Invoice.id == invoice_id, Invoice.company_id == company_id)
    )
    invoice = result.scalar_one_or_none()
    if invoice is None:
        raise InvoiceNotFoundError("Fatura nao encontrada")

    lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))
    lines = list(lines_result.scalars().all())
    return invoice, lines