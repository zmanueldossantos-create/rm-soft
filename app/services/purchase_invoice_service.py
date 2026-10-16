"""
Faturas de compra (point 12) - the supplier invoices the company registers (see PurchaseInvoice).

- register: the supplier, its document number and date, the period (internal entry: the active one, or the
  soft-closed one for a late invoice), the lines (a product, a service or a free text; quantity; price without VAT;
  the legal VAT rate the supplier charged, with its exemption motive when exempt). The VAT is split into what the
  company may deduct and what is a cost, by the deductible share of the company's regime (data, never code).
- the same supplier document is never registered twice (unless the first registration was cancelled).
- cancel: a registration is never deleted - it is cancelled with its reason, and leaves the totals.
- stock (optional, chosen at registration): the products of the invoice enter a warehouse in the SAME transaction - the
  system's automatic entry document (EA), each product at its line's cost per base unit (HT + non-deductible VAT: what
  the company really pays), which moves the weighted average cost. A product line is bought in one of the product's
  units (10 SC of 20 kg = 200 KG). Its cancellation takes the same quantities out of that warehouse (an automatic
  exit, SA) - refused when the stock is no longer there. One purchase, one entry: no separate Receção.
- SAF-T: the supplier document's type (FT, FR, TV; NC - a credit note, which refers to an invoice of the same supplier,
  never moves the stock and counts against the deductible VAT), its printed hash, and per line what the deductible VAT
  is for (MFI, INV, OBC, SERV, IMPT, SCE - by default from the line: a product INV, a service SERV, the rest OBC).
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.fiscal_regime import FiscalRegime
from app.models.fiscal_year import FiscalYear
from app.models.legal_vat_rate import LegalVatRate
from app.models.movement_type import MovementDirection
from app.models.product import Product
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
from app.models.service import Service
from app.models.supplier import Supplier
from app.models.user import User
from app.models.stock_movement_document import StockMovementDocument
from app.models.vat_code import VatCode
from app.models.warehouse import Warehouse
from app.models.stock_movement_document import StockMovementDocumentLine
from app.services.fiscal_period_service import MONTH_NAMES_PT, PeriodClosedError, resolve_posting_period
from app.services.movement_document_service import (
    EmptyMovementError, InsufficientStockForMovementError, MovementProductNotFoundError, MovementTypeNotConfiguredError,
    MovementWarehouseNotFoundError, create_stock_movement_document, get_automatic_movement_type,
)
from app.services.product_sale_unit_service import SaleUnitInvalidError, resolve_line_unit

_STOCK_ERRORS = (EmptyMovementError, InsufficientStockForMovementError, MovementProductNotFoundError,
                 MovementTypeNotConfiguredError, MovementWarehouseNotFoundError)


# the supplier documents a purchase may be registered from (SAF-T PurchaseType) and the destinations of the
# deductible VAT (SAF-T DeductibleTaxType)
PURCHASE_TYPES = {"FT": "Fatura", "FR": "Fatura-recibo", "TV": "Talão de venda", "NC": "Nota de crédito"}
DEDUCTIBLE_TAX_TYPES = {"MFI": "Meios fixos e investimentos", "INV": "Existências", "OBC": "Outros bens de consumo",
                        "SERV": "Serviços", "IMPT": "Importação", "SCE": "Serviços contratados no estrangeiro"}


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
    description: str | None = None, stock_entry: bool = False, warehouse_id: uuid.UUID | None = None,
    purchase_type: str = "FT", supplier_hash: str | None = None, reference_invoice_id: uuid.UUID | None = None,
) -> PurchaseInvoice:
    """
    lines: [{product_id | service_id | None, sale_unit_id, description, quantity, unit_price, legal_vat_rate_id,
    exemption_id}] - quantity and price in the line's unit (sale_unit_id: one of the product's; None: its base unit).
    stock_entry: its products enter warehouse_id (see the module docstring).
    """
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
    if purchase_type not in PURCHASE_TYPES:
        raise PurchaseInvoiceError("Tipo de documento do fornecedor inválido")
    supplier_hash = "".join((supplier_hash or "").split()) or None
    if supplier_hash is not None and len(supplier_hash) > 4:
        raise PurchaseInvoiceError("O hash do documento tem no máximo 4 caracteres")
    if purchase_type == "NC":
        # a credit note corrects a registered invoice of the same supplier - and never moves the stock
        original = (await db.execute(select(PurchaseInvoice).where(
            PurchaseInvoice.id == reference_invoice_id, PurchaseInvoice.company_id == company_id,
            PurchaseInvoice.supplier_id == supplier_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
            PurchaseInvoice.purchase_type != "NC",
        ))).scalar_one_or_none() if reference_invoice_id else None
        if original is None:
            raise PurchaseInvoiceError("Indique a fatura deste fornecedor que a nota de crédito corrige")
        if stock_entry:
            raise PurchaseInvoiceError("Uma nota de crédito não dá entrada em stock")
    else:
        reference_invoice_id = None

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
            try:  # the unit it was bought in - the same conversion as sales and receptions
                _price, factor, sale_unit_id, unit_code = await resolve_line_unit(
                    db, company_id, product, line.get("sale_unit_id"), quantity)
            except SaleUnitInvalidError as e:
                raise PurchaseInvoiceError(f"Linha {position}: {e}")
        elif service_id is not None:
            service = (await db.execute(select(Service).where(Service.id == service_id, Service.company_id == company_id))).scalar_one_or_none()
            if service is None:
                raise PurchaseInvoiceError(f"Linha {position}: serviço não encontrado")
            text = text or service.name
        if product_id is None:
            sale_unit_id, unit_code, factor = None, None, 1.0
        destination = line.get("deductible_tax_type") or ("INV" if product_id else "SERV" if service_id else "OBC")
        if destination not in DEDUCTIBLE_TAX_TYPES:
            raise PurchaseInvoiceError(f"Linha {position}: destino do IVA inválido")
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
            sale_unit_id=sale_unit_id, unit_snapshot=unit_code, unit_factor=factor, quantity=quantity, unit_price=unit_price, legal_vat_rate_id=rate.id, tax_category=rate.tax_category,
            vat_rate=rate.rate, exemption_id=exemption_id, line_subtotal=subtotal, line_vat=vat,
            line_total=_money(subtotal + vat), vat_deductible=deductible, vat_non_deductible=non_deductible,
            cost=_money(subtotal + non_deductible), deductible_tax_type=destination,
        ))

    series = f"COMP{year}"
    last = (await db.execute(
        select(func.max(PurchaseInvoice.number)).where(PurchaseInvoice.company_id == company_id, PurchaseInvoice.series == series)
    )).scalar_one()
    invoice = PurchaseInvoice(
        company_id=company_id, supplier_id=supplier_id, fiscal_period_id=period.id, series=series, number=(last or 0) + 1,
        supplier_document=supplier_document, document_date=document_date, due_date=due_date,
        purchase_type=purchase_type, supplier_hash=supplier_hash, reference_invoice_id=reference_invoice_id,
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

    if stock_entry:
        stock_lines = [r for r in line_rows if r.product_id is not None]
        if not stock_lines:
            await db.rollback()
            raise PurchaseInvoiceError("A entrada em stock precisa de pelo menos uma linha de produto")
        warehouse = (await db.execute(
            select(Warehouse).where(Warehouse.id == warehouse_id, Warehouse.company_id == company_id)
        )).scalar_one_or_none() if warehouse_id else None
        if warehouse is None or not warehouse.is_active:
            await db.rollback()
            raise PurchaseInvoiceError("Escolha o armazém de entrada da mercadoria")
        try:  # each product at its cost per unit bought (HT + non-deductible VAT) - the weighted average cost
            movement_type = await get_automatic_movement_type(db, MovementDirection.ENTRADA)
            document = await create_stock_movement_document(
                db, company_id, movement_type.id, warehouse.id,
                [{"product_id": r.product_id, "sale_unit_id": r.sale_unit_id, "quantity": float(r.quantity),
                  "purchase_price": float(r.cost) / float(r.quantity)} for r in stock_lines],
                movement_date=document_date, description=_stock_text(invoice, supplier.name),
                supplier_id=supplier_id, fiscal_period_id=period.id, system=True, commit=False,
            )
        except _STOCK_ERRORS as e:
            await db.rollback()
            raise PurchaseInvoiceError(str(e))
        invoice.warehouse_id = warehouse.id
        invoice.stock_entry_document_id = document.id

    await db.commit()
    await db.refresh(invoice)
    return invoice


def _stock_text(invoice: PurchaseInvoice, supplier_name: str) -> str:
    return f"Fatura de compra {invoice.series}/{invoice.number} - {supplier_name} {invoice.supplier_document}"[:300]


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
    credit_note = (await db.execute(select(PurchaseInvoice.series, PurchaseInvoice.number).where(
        PurchaseInvoice.reference_invoice_id == invoice.id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
    ))).first()
    if credit_note is not None:
        raise PurchaseInvoiceError(f"Anule primeiro a nota de crédito {credit_note[0]}/{credit_note[1]} desta fatura")
    from app.models.supplier_payment import SupplierPayment, SupplierPaymentAllocation, SupplierPaymentStatus
    payment = (await db.execute(select(SupplierPayment.series, SupplierPayment.number)
                                .join(SupplierPaymentAllocation, SupplierPaymentAllocation.payment_id == SupplierPayment.id)
                                .where(SupplierPaymentAllocation.purchase_invoice_id == invoice.id,
                                       SupplierPayment.status == SupplierPaymentStatus.REGISTADO))).first()
    if payment is not None:  # what was paid on it must be cancelled first
        raise PurchaseInvoiceError(f"Anule primeiro o pagamento {payment[0]}/{payment[1]} desta fatura")
    if invoice.stock_entry_document_id is not None:
        # its products leave the warehouse they entered - in the active period, today; refused if no longer there
        entry_lines = (await db.execute(
            select(StockMovementDocumentLine).where(StockMovementDocumentLine.document_id == invoice.stock_entry_document_id)
        )).scalars().all()
        supplier_name = (await db.execute(select(Supplier.name).where(Supplier.id == invoice.supplier_id))).scalar_one()
        try:  # in base units: the quantities that entered, whatever became of the unit since
            movement_type = await get_automatic_movement_type(db, MovementDirection.SAIDA)
            document = await create_stock_movement_document(
                db, company_id, movement_type.id, invoice.warehouse_id,
                [{"product_id": l.product_id, "quantity": float(l.quantity) * float(l.unit_factor)} for l in entry_lines],
                description=("Anulação da " + _stock_text(invoice, supplier_name))[:300],
                supplier_id=invoice.supplier_id, system=True, commit=False,
            )
        except _STOCK_ERRORS as e:
            await db.rollback()
            raise PurchaseInvoiceError(f"Não é possível anular: {e}")
        invoice.stock_exit_document_id = document.id
    invoice.status = PurchaseInvoiceStatus.ANULADA
    invoice.cancel_reason = reason[:300]
    invoice.cancelled_at = datetime.now(timezone.utc)
    invoice.cancelled_by_user_id = user_id
    await db.commit()
    await db.refresh(invoice)
    return invoice


def _summary(invoice: PurchaseInvoice, supplier: Supplier, period_label: str, balance: dict | None = None) -> dict:
    balance = balance or {}
    return {
        # what is paid and still owed on it (supplier_payment_service.invoice_balances)
        "amount_paid": balance.get("paid", 0.0), "amount_credited": balance.get("credited", 0.0),
        "amount_due": balance.get("due", 0.0), "payment_status": balance.get("payment_status"),
        "overdue": balance.get("overdue", False),
        "id": invoice.id, "reference": f"{invoice.series}/{invoice.number}", "status": invoice.status.value,
        "purchase_type": invoice.purchase_type, "supplier_hash": invoice.supplier_hash,
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
    from app.services.supplier_payment_service import invoice_balances
    balances = await invoice_balances(db, [i for i, _ in rows])
    return [_summary(invoice, supplier, labels.get(invoice.fiscal_period_id, "-"), balances.get(invoice.id))
            for invoice, supplier in rows]


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
    reference_label = None
    if invoice.reference_invoice_id:
        ref = (await db.execute(select(PurchaseInvoice).where(PurchaseInvoice.id == invoice.reference_invoice_id))).scalar_one()
        reference_label = f"{ref.series}/{ref.number} · {ref.supplier_document}"
    stock_docs = {d.id: f"{d.series}/{d.number}" for d in (await db.execute(select(StockMovementDocument).where(
        StockMovementDocument.id.in_([d for d in (invoice.stock_entry_document_id, invoice.stock_exit_document_id) if d]))
    )).scalars().all()}
    warehouse_name = (await db.execute(select(Warehouse.name).where(Warehouse.id == invoice.warehouse_id))).scalar_one_or_none() \
        if invoice.warehouse_id else None
    from app.services.supplier_payment_service import invoice_balances
    balance = (await invoice_balances(db, [invoice])).get(invoice.id)
    return {
        **_summary(invoice, supplier, labels.get(invoice.fiscal_period_id, "-"), balance),
        "created_by": names.get(invoice.created_by_user_id), "cancelled_by": names.get(invoice.cancelled_by_user_id),
        "cancelled_at": invoice.cancelled_at, "warehouse_name": warehouse_name,
        "reference_invoice": reference_label,
        "stock_entry_reference": stock_docs.get(invoice.stock_entry_document_id),
        "stock_exit_reference": stock_docs.get(invoice.stock_exit_document_id),
        "lines": [{
            "position": l.position, "product_id": l.product_id, "service_id": l.service_id, "description": l.description,
            "unit": l.unit_snapshot, "quantity": float(l.quantity), "unit_price": float(l.unit_price), "tax_category": l.tax_category,
            "vat_rate": float(l.vat_rate), "exemption_code": code, "line_subtotal": float(l.line_subtotal),
            "line_vat": float(l.line_vat), "line_total": float(l.line_total), "vat_deductible": float(l.vat_deductible),
            "vat_non_deductible": float(l.vat_non_deductible), "cost": float(l.cost),
            "deductible_tax_type": l.deductible_tax_type,
        } for l, code in lines],
    }
