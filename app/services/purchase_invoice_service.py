"""
Faturas de compra (point 12) - the supplier invoices the company registers (see PurchaseInvoice).

- register: the supplier, its document number and date, the period (internal entry: the active one, or the
  soft-closed one for a late invoice), the lines (a product, a service or a free text; quantity; price without VAT;
  the legal VAT rate the supplier charged, with its exemption motive when exempt). The VAT is split into what the
  company may deduct and what is a cost, by the deductible share of the company's regime (data, never code).
- the same supplier document is never registered twice (unless the first registration was cancelled).
- cancel: a registration is never deleted - it is cancelled with its reason, and leaves the totals.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.fiscal_regime import FiscalRegime
from app.models.fiscal_year import FiscalYear
from app.models.legal_vat_rate import LegalVatRate
from app.models.product import Product
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
from app.models.service import Service
from app.models.supplier import Supplier
from app.models.user import User
from app.models.vat_code import VatCode
from app.services.fiscal_period_service import MONTH_NAMES_PT, PeriodClosedError, resolve_posting_period


class PurchaseInvoiceError(Exception):
    """A purchase invoice that cannot be registered or changed as asked."""


class PurchaseInvoiceNotFoundError(Exception):
    pass


def _money(value: float) -> float:
    return round(value + 0.0, 2)


async def _deductible_pct(db: AsyncSession, company_id: uuid.UUID) -> float:
    """The share of purchase VAT the company may deduct - its regime's; 100 % for a company without a regime."""
    pct = (await db.execute(
        select(FiscalRegime.input_vat_deductible_pct).join(Company, Company.fiscal_regime_id == FiscalRegime.id)
        .where(Company.id == company_id)
    )).scalar_one_or_none()
    return float(pct) if pct is not None else 100.0


async def register_purchase_invoice(
    db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID, supplier_id: uuid.UUID, supplier_document: str,
    document_date: date, lines: list[dict], fiscal_period_id: uuid.UUID | None = None, due_date: date | None = None,
    description: str | None = None,
) -> PurchaseInvoice:
    """lines: [{product_id | service_id | None, description, quantity, unit_price, legal_vat_rate_id, exemption_id}]"""
    supplier = (await db.execute(
        select(Supplier).where(Supplier.id == supplier_id, Supplier.company_id == company_id)
    )).scalar_one_or_none()
    if supplier is None:
        raise PurchaseInvoiceError("Fornecedor não encontrado")
    supplier_document = " ".join((supplier_document or "").split())
    if not supplier_document:
        raise PurchaseInvoiceError("Indique o número do documento do fornecedor")
    if not lines:
        raise PurchaseInvoiceError("A fatura deve ter pelo menos uma linha")
    duplicate = (await db.execute(
        select(PurchaseInvoice.series, PurchaseInvoice.number).where(
            PurchaseInvoice.company_id == company_id, PurchaseInvoice.supplier_id == supplier_id,
            func.upper(PurchaseInvoice.supplier_document) == supplier_document.upper(),
            PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
        )
    )).first()
    if duplicate is not None:
        raise PurchaseInvoiceError(
            f"O documento {supplier_document} deste fornecedor já está registado ({duplicate[0]}/{duplicate[1]})")

    # booked like every internal entry; its date is the supplier's, never in the future nor before its period
    period = await resolve_posting_period(db, company_id, fiscal_period_id)
    year = (await db.execute(select(FiscalYear.year).where(FiscalYear.id == period.fiscal_year_id))).scalar_one()
    if document_date > date.today():
        raise PeriodClosedError("A data do documento não pode ser futura")
    if document_date < date(year, period.month, 1):
        raise PeriodClosedError(
            f"A data do documento ({document_date.strftime('%d/%m/%Y')}) é anterior ao período escolhido "
            f"({MONTH_NAMES_PT[period.month]} de {year})")
    if due_date is not None and due_date < document_date:
        raise PurchaseInvoiceError("O vencimento não pode ser anterior à data do documento")

    pct = await _deductible_pct(db, company_id)
    rates = {r.id: r for r in (await db.execute(select(LegalVatRate))).scalars().all()}
    line_rows, totals = [], {"subtotal": 0.0, "vat": 0.0, "deductible": 0.0, "non_deductible": 0.0}
    for position, line in enumerate(lines, start=1):
        quantity, unit_price = float(line.get("quantity") or 0), float(line.get("unit_price") or 0)
        if quantity <= 0:
            raise PurchaseInvoiceError(f"Linha {position}: a quantidade deve ser maior que zero")
        if unit_price < 0:
            raise PurchaseInvoiceError(f"Linha {position}: o preço não pode ser negativo")
        rate = rates.get(line.get("legal_vat_rate_id"))
        if rate is None:
            raise PurchaseInvoiceError(f"Linha {position}: escolha a taxa de IVA do fornecedor")
        exemption_id = line.get("exemption_id")
        if float(rate.rate) == 0 and exemption_id is None:
            raise PurchaseInvoiceError(f"Linha {position}: uma linha isenta de IVA precisa do motivo de isenção")
        if float(rate.rate) != 0:
            exemption_id = None
        elif (await db.execute(select(VatCode.id).where(VatCode.id == exemption_id))).scalar_one_or_none() is None:
            raise PurchaseInvoiceError(f"Linha {position}: motivo de isenção inválido")

        # the line's own text - never the invoice's description (a parameter of this function)
        product_id, service_id, text = line.get("product_id"), line.get("service_id"), (line.get("description") or "").strip()
        if product_id is not None:
            product = (await db.execute(select(Product).where(Product.id == product_id, Product.company_id == company_id))).scalar_one_or_none()
            if product is None:
                raise PurchaseInvoiceError(f"Linha {position}: produto não encontrado")
            text = text or product.name
            service_id = None
        elif service_id is not None:
            service = (await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))).scalar_one_or_none()
            if service is None:
                raise PurchaseInvoiceError(f"Linha {position}: serviço não encontrado")
            text = text or service.name
        if not text:
            raise PurchaseInvoiceError(f"Linha {position}: indique a descrição")

        subtotal = _money(quantity * unit_price)
        vat = _money(subtotal * float(rate.rate) / 100)
        deductible = _money(vat * pct / 100)
        non_deductible = _money(vat - deductible)
        totals["subtotal"] += subtotal
        totals["vat"] += vat
        totals["deductible"] += deductible
        totals["non_deductible"] += non_deductible
        line_rows.append(PurchaseInvoiceLine(
            position=position, product_id=product_id, service_id=service_id, description=text[:255],
            quantity=quantity, unit_price=unit_price, legal_vat_rate_id=rate.id, tax_category=rate.tax_category,
            vat_rate=rate.rate, exemption_id=exemption_id, line_subtotal=subtotal, line_vat=vat,
            line_total=_money(subtotal + vat), vat_deductible=deductible, vat_non_deductible=non_deductible,
            cost=_money(subtotal + non_deductible),
        ))

    series = f"COMP{year}"
    last = (await db.execute(
        select(func.max(PurchaseInvoice.number)).where(PurchaseInvoice.company_id == company_id, PurchaseInvoice.series == series)
    )).scalar_one()
    invoice = PurchaseInvoice(
        company_id=company_id, supplier_id=supplier_id, fiscal_period_id=period.id, series=series, number=(last or 0) + 1,
        supplier_document=supplier_document, document_date=document_date, due_date=due_date,
        description=(description or None), subtotal=_money(totals["subtotal"]), vat_total=_money(totals["vat"]),
        total=_money(totals["subtotal"] + totals["vat"]), deductible_pct=pct, vat_deductible=_money(totals["deductible"]),
        vat_non_deductible=_money(totals["non_deductible"]), status=PurchaseInvoiceStatus.REGISTADA,
        created_by_user_id=user_id,
    )
    db.add(invoice)
    await db.flush()
    for row in line_rows:
        row.purchase_invoice_id = invoice.id
        db.add(row)
    await db.commit()
    await db.refresh(invoice)
    return invoice


async def _get(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID) -> PurchaseInvoice:
    invoice = (await db.execute(
        select(PurchaseInvoice).where(PurchaseInvoice.id == invoice_id, PurchaseInvoice.company_id == company_id)
    )).scalar_one_or_none()
    if invoice is None:
        raise PurchaseInvoiceNotFoundError("Fatura de compra não encontrada")
    return invoice


async def cancel_purchase_invoice(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID, user_id: uuid.UUID,
                                  reason: str) -> PurchaseInvoice:
    invoice = await _get(db, company_id, invoice_id)
    if invoice.status == PurchaseInvoiceStatus.ANULADA:
        raise PurchaseInvoiceError("Esta fatura de compra já está anulada")
    reason = " ".join((reason or "").split())
    if not reason:
        raise PurchaseInvoiceError("Indique o motivo da anulação")
    invoice.status = PurchaseInvoiceStatus.ANULADA
    invoice.cancel_reason = reason[:300]
    invoice.cancelled_at = datetime.now(timezone.utc)
    invoice.cancelled_by_user_id = user_id
    await db.commit()
    await db.refresh(invoice)
    return invoice


def _summary(invoice: PurchaseInvoice, supplier: Supplier, period_label: str) -> dict:
    return {
        "id": invoice.id, "reference": f"{invoice.series}/{invoice.number}", "status": invoice.status.value,
        "supplier_id": supplier.id, "supplier_name": supplier.name, "supplier_nif": supplier.nif,
        "supplier_document": invoice.supplier_document, "document_date": invoice.document_date, "due_date": invoice.due_date,
        "period_label": period_label, "description": invoice.description,
        "subtotal": float(invoice.subtotal), "vat_total": float(invoice.vat_total), "total": float(invoice.total),
        "deductible_pct": float(invoice.deductible_pct), "vat_deductible": float(invoice.vat_deductible),
        "vat_non_deductible": float(invoice.vat_non_deductible), "created_at": invoice.created_at,
        "cancel_reason": invoice.cancel_reason,
    }


async def _period_labels(db: AsyncSession, period_ids) -> dict:
    from app.models.fiscal_period import FiscalPeriod
    if not period_ids:
        return {}
    return {pid: f"{MONTH_NAMES_PT[month]} {year}" for pid, month, year in (await db.execute(
        select(FiscalPeriod.id, FiscalPeriod.month, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id.in_(list(period_ids)))
    )).all()}


async def list_purchase_invoices(
    db: AsyncSession, company_id: uuid.UUID, supplier_id: uuid.UUID | None = None, fiscal_period_id: uuid.UUID | None = None,
    status: PurchaseInvoiceStatus | None = None, date_from: date | None = None, date_to: date | None = None,
) -> list[dict]:
    """The registered (and cancelled) purchase invoices, most recent first."""
    query = select(PurchaseInvoice, Supplier).join(Supplier, Supplier.id == PurchaseInvoice.supplier_id).where(
        PurchaseInvoice.company_id == company_id)
    if supplier_id is not None:
        query = query.where(PurchaseInvoice.supplier_id == supplier_id)
    if fiscal_period_id is not None:
        query = query.where(PurchaseInvoice.fiscal_period_id == fiscal_period_id)
    if status is not None:
        query = query.where(PurchaseInvoice.status == status)
    if date_from is not None:
        query = query.where(PurchaseInvoice.document_date >= date_from)
    if date_to is not None:
        query = query.where(PurchaseInvoice.document_date <= date_to)
    rows = (await db.execute(query.order_by(PurchaseInvoice.document_date.desc(), PurchaseInvoice.number.desc()))).all()
    labels = await _period_labels(db, {i.fiscal_period_id for i, _ in rows})
    return [_summary(invoice, supplier, labels.get(invoice.fiscal_period_id, "-")) for invoice, supplier in rows]


async def get_purchase_invoice(db: AsyncSession, company_id: uuid.UUID, invoice_id: uuid.UUID) -> dict:
    invoice = await _get(db, company_id, invoice_id)
    supplier = (await db.execute(select(Supplier).where(Supplier.id == invoice.supplier_id))).scalar_one()
    labels = await _period_labels(db, {invoice.fiscal_period_id})
    lines = (await db.execute(
        select(PurchaseInvoiceLine, VatCode.code).outerjoin(VatCode, VatCode.id == PurchaseInvoiceLine.exemption_id)
        .where(PurchaseInvoiceLine.purchase_invoice_id == invoice.id).order_by(PurchaseInvoiceLine.position)
    )).all()
    names = dict((await db.execute(select(User.id, User.full_name).where(
        User.id.in_([u for u in (invoice.created_by_user_id, invoice.cancelled_by_user_id) if u]))
    )).all())
    return {
        **_summary(invoice, supplier, labels.get(invoice.fiscal_period_id, "-")),
        "created_by": names.get(invoice.created_by_user_id), "cancelled_by": names.get(invoice.cancelled_by_user_id),
        "cancelled_at": invoice.cancelled_at,
        "lines": [{
            "position": l.position, "product_id": l.product_id, "service_id": l.service_id, "description": l.description,
            "quantity": float(l.quantity), "unit_price": float(l.unit_price), "tax_category": l.tax_category,
            "vat_rate": float(l.vat_rate), "exemption_code": code, "line_subtotal": float(l.line_subtotal),
            "line_vat": float(l.line_vat), "line_total": float(l.line_total), "vat_deductible": float(l.vat_deductible),
            "vat_non_deductible": float(l.vat_non_deductible), "cost": float(l.cost),
        } for l, code in lines],
    }
