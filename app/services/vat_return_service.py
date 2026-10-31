"""
Apuramento do IVA (point 12, step 4) - the VAT of a month: what the company charged on its sales, what it may deduct
on its purchases, and the result (to pay, or a credit).

- IVA liquidado: the lines of the sales documents dated in the month (business_date, the same selection as the SAF-T):
  Fatura, Fatura-Recibo and Nota de Débito add, Nota de Crédito subtracts; pro-formas and receipts carry no VAT. Each
  line at the amounts the SAF-T declares - after its share of the document's global discount (split_global_discount).
  Every activity of the company (Hotel, Padaria, Bar...) - one NIF, one return. Grouped by tax code, rate and
  exemption motive.
- IVA dedutível: the purchase invoices booked in the period (REGISTADA), with the deductible share computed when they
  were registered (the regime of that day) - a supplier's credit note (NC) counting against. Grouped the same way.
- The formula follows the company's regime - data of the regime, never code:
      to pay = IVA liquidado + sales base x turnover_vat_pct - IVA dedutível
  Regime Geral (0 %, 100 % deductible): liquidado - dedutível. Simplificado (sales exempt M00, 7 % of the turnover,
  7 % deductible): turnover x 7 % - IVA suportado x 7 %, the turnover leaving out the sales exempt for a reason the
  regime keeps (kept_exemption_ids: M11 medicines...). Exclusão (0 %, 0 %): nothing - no return in this regime.
  Positive: IVA a pagar; negative: crédito de IVA (its carry-over to the next month is not handled here).
"""
import uuid
from calendar import monthrange
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.customer import Customer
from app.models.document_type import DocumentType
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_regime import FiscalRegime
from app.models.fiscal_year import FiscalYear
from app.models.invoice import Invoice, InvoiceType
from app.models.invoice_line import InvoiceLine
from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
from app.models.supplier import Supplier
from app.models.vat_code import VatCode
from app.services.company_service import regime_on
from app.services.document_amounts import split_global_discount
from app.services.fiscal_period_service import MONTH_NAMES_PT
from app.utils.saf_t_generator import INVOICE_TYPE_MAP

# the sales documents that carry VAT, and their sign in the return
SALES_SIGN = {InvoiceType.FACTURA: 1, InvoiceType.FACTURA_RECIBO: 1, InvoiceType.NOTA_DEBITO: 1, InvoiceType.NOTA_CREDITO: -1}


class VatReturnError(Exception):
    pass


def _money(value: float) -> float:
    return round(value + 0.0, 2)


async def _period(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> tuple[FiscalPeriod, int, date, date]:
    row = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.id == period_id, FiscalPeriod.company_id == company_id)
    )).first()
    if row is None:
        raise VatReturnError("Período não encontrado")
    period, year = row
    return period, year, date(year, period.month, 1), date(year, period.month, monthrange(year, period.month)[1])


async def list_vat_periods(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """Every period of the company, most recent first."""
    rows = (await db.execute(
        select(FiscalPeriod, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(FiscalPeriod.company_id == company_id).order_by(FiscalYear.year.desc(), FiscalPeriod.month.desc())
    )).all()
    return [{"id": p.id, "label": f"{MONTH_NAMES_PT[p.month]} {year}", "status": p.status} for p, year in rows]


def _group_key(code: str | None, rate: float, exemption: str | None) -> tuple:
    return (code or ("ISE" if rate == 0 else "-"), rate, exemption or None)


async def _sales_lines(db: AsyncSession, company_id: uuid.UUID, start: date, end: date) -> list[tuple]:
    """(invoice, group key, signed base, signed VAT) for each sales line of the month - the declared amounts: after the
    document's global discount, spread over its lines like the SAF-T does (lines in the document's order)."""
    invoices = {i.id: i for i in (await db.execute(select(Invoice).where(
        Invoice.company_id == company_id, Invoice.business_date >= start, Invoice.business_date <= end,
        Invoice.invoice_type.in_(list(SALES_SIGN)),
        Invoice.issuance_mode != "FORMACAO",  # Modo formação: no fiscal value
    ))).scalars().all()}
    if not invoices:
        return []
    by_invoice: dict[uuid.UUID, list[InvoiceLine]] = {}
    for line in (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id.in_(list(invoices)))
                                  .order_by(InvoiceLine.created_at, InvoiceLine.id))).scalars().all():
        by_invoice.setdefault(line.invoice_id, []).append(line)
    out = []
    for invoice_id, lines in by_invoice.items():
        invoice = invoices[invoice_id]
        sign = SALES_SIGN[invoice.invoice_type]
        amounts = [(float(l.line_subtotal), float(l.line_vat)) for l in lines]
        discount = float(invoice.discount_global_percent or 0)
        if discount:
            split = split_global_discount([(float(l.line_subtotal), float(l.vat_rate_snapshot)) for l in lines],
                                          discount, float(invoice.total))
            amounts = [(part["net"], part["vat"]) for part in split["lines"]]
        for line, (base, vat) in zip(lines, amounts):
            key = _group_key(line.tax_code_snapshot, float(line.vat_rate_snapshot), line.exemption_code)
            out.append((invoice, key, sign * base, sign * vat))
    return out


async def get_vat_return(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID) -> dict:
    period, year, start, end = await _period(db, company_id, period_id)

    # IVA liquidado - the sales lines of the month, a credit note counting against
    sales: dict[tuple, dict] = {}
    for invoice, key, base, vat in await _sales_lines(db, company_id, start, end):
        group = sales.setdefault(key, {"base": 0.0, "vat": 0.0, "documents": set()})
        group["base"] += base
        group["vat"] += vat
        group["documents"].add(invoice.id)

    # IVA dedutível - the purchase invoices booked in the period
    purchases: dict[tuple, dict] = {}
    rows = (await db.execute(
        select(PurchaseInvoiceLine.tax_category, PurchaseInvoiceLine.vat_rate, VatCode.code, PurchaseInvoiceLine.line_subtotal,
               PurchaseInvoiceLine.line_vat, PurchaseInvoiceLine.vat_deductible, PurchaseInvoice.id, PurchaseInvoice.purchase_type)
        .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id)
        .outerjoin(VatCode, VatCode.id == PurchaseInvoiceLine.exemption_id)
        .where(PurchaseInvoice.company_id == company_id, PurchaseInvoice.fiscal_period_id == period.id,
               PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA)
    )).all()
    for code, rate, exemption, base, vat, deductible, invoice_id, purchase_type in rows:
        sign = -1 if purchase_type == "NC" else 1
        group = purchases.setdefault(_group_key(code, float(rate), exemption),
                                     {"base": 0.0, "vat": 0.0, "deductible": 0.0, "documents": set()})
        group["base"] += sign * float(base)
        group["vat"] += sign * float(vat)
        group["deductible"] += sign * float(deductible)
        group["documents"].add(invoice_id)

    def lines(groups: dict, with_deductible: bool) -> list[dict]:
        out = []
        for (code, rate, exemption), g in sorted(groups.items(), key=lambda kv: (-kv[0][1], kv[0][0], kv[0][2] or "")):
            line = {"tax_code": code, "rate": rate, "exemption_code": exemption, "base": _money(g["base"]),
                    "vat": _money(g["vat"]), "documents": len(g["documents"])}
            if with_deductible:
                line["deductible"] = _money(g["deductible"])
            out.append(line)
        return out

    sales_lines, purchase_lines = lines(sales, False), lines(purchases, True)
    sales_base = _money(sum(l["base"] for l in sales_lines))
    output_vat = _money(sum(l["vat"] for l in sales_lines))
    input_vat = _money(sum(l["vat"] for l in purchase_lines))
    deductible = _money(sum(l["deductible"] for l in purchase_lines))

    # the regime in force at the end of the month (its history), else the company's current one
    regime = await regime_on(db, company_id, end)
    if regime is None:
        regime = (await db.execute(select(FiscalRegime).join(Company, Company.fiscal_regime_id == FiscalRegime.id)
                                   .where(Company.id == company_id))).scalar_one_or_none()
    turnover_pct = float(regime.turnover_vat_pct) if regime is not None else 0.0
    # The sales exempt for a reason the regime keeps (M11 medicines...) stay out of the turnover base.
    kept_codes: set[str] = set()
    if regime is not None and regime.kept_exemption_ids:
        kept_codes = set((await db.execute(
            select(VatCode.code).where(VatCode.id.in_(regime.kept_exemption_ids))
        )).scalars().all())
    turnover_excluded = _money(sum(l["base"] for l in sales_lines if l["exemption_code"] in kept_codes))
    turnover_base = _money(sales_base - turnover_excluded)
    turnover_vat = _money(turnover_base * turnover_pct / 100)
    result = _money(output_vat + turnover_vat - deductible)
    # no VAT charged, none on the turnover and none deductible: the regime has no return (Exclusão)
    no_return = regime is not None and turnover_pct == 0 and float(regime.input_vat_deductible_pct) == 0 and output_vat == 0

    return {
        "period_id": period.id, "period_label": f"{MONTH_NAMES_PT[period.month]} {year}", "period_status": period.status,
        "date_from": start, "date_to": end,
        "regime_name": regime.name if regime is not None else None, "turnover_vat_pct": turnover_pct,
        "input_vat_deductible_pct": float(regime.input_vat_deductible_pct) if regime is not None else 100.0,
        "sales": sales_lines, "purchases": purchase_lines,
        "sales_base": sales_base, "output_vat": output_vat, "turnover_vat": turnover_vat,
        "turnover_base": turnover_base, "turnover_excluded": turnover_excluded,
        "turnover_excluded_codes": sorted(kept_codes) if turnover_excluded else [],
        "purchases_base": _money(sum(l["base"] for l in purchase_lines)), "input_vat": input_vat, "deductible_vat": deductible,
        "result": result, "to_pay": max(result, 0.0), "credit": max(-result, 0.0), "no_return": no_return,
    }


async def list_vat_documents(db: AsyncSession, company_id: uuid.UUID, period_id: uuid.UUID, side: str,
                             tax_code: str, rate: float, exemption_code: str | None = None) -> list[dict]:
    """The documents behind one line of the return (side: sales | purchases) - each with its amounts at that rate."""
    period, _year, start, end = await _period(db, company_id, period_id)
    wanted = _group_key(tax_code, float(rate), exemption_code)
    docs: dict[uuid.UUID, dict] = {}
    if side == "sales":
        doc_codes = dict((await db.execute(select(DocumentType.id, DocumentType.code))).all())
        rows = [r for r in await _sales_lines(db, company_id, start, end) if r[1] == wanted]
        customer_ids = {r[0].customer_id for r in rows if r[0].customer_id}
        customers = dict((await db.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids)))).all()) \
            if customer_ids else {}
        for invoice, _key, base, vat in rows:
            doc = docs.setdefault(invoice.id, {
                "id": invoice.id, "reference": f"{doc_codes.get(invoice.document_type_id) or INVOICE_TYPE_MAP.get(invoice.invoice_type.value, '')} "
                             f"{invoice.series}/{invoice.number}".strip(),
                "date": invoice.business_date, "party": customers.get(invoice.customer_id, "Consumidor final"),
                "base": 0.0, "vat": 0.0})
            doc["base"] += base
            doc["vat"] += vat
    elif side == "purchases":
        rows = (await db.execute(
            select(PurchaseInvoice, Supplier.name, PurchaseInvoiceLine.tax_category, PurchaseInvoiceLine.vat_rate, VatCode.code,
                   PurchaseInvoiceLine.line_subtotal, PurchaseInvoiceLine.line_vat, PurchaseInvoiceLine.vat_deductible)
            .join(PurchaseInvoice, PurchaseInvoice.id == PurchaseInvoiceLine.purchase_invoice_id)
            .join(Supplier, Supplier.id == PurchaseInvoice.supplier_id)
            .outerjoin(VatCode, VatCode.id == PurchaseInvoiceLine.exemption_id)
            .where(PurchaseInvoice.company_id == company_id, PurchaseInvoice.fiscal_period_id == period.id,
                   PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA)
        )).all()
        for invoice, supplier, code, line_rate, exemption, base, vat, deductible in rows:
            if _group_key(code, float(line_rate), exemption) != wanted:
                continue
            doc = docs.setdefault(invoice.id, {
                "id": invoice.id, "reference": f"{invoice.series}/{invoice.number} · {invoice.supplier_document}", "date": invoice.document_date,
                "party": supplier, "base": 0.0, "vat": 0.0, "deductible": 0.0})
            sign = -1 if invoice.purchase_type == "NC" else 1
            doc["base"] += sign * float(base)
            doc["vat"] += sign * float(vat)
            doc["deductible"] += sign * float(deductible)
    else:
        raise VatReturnError("Lado inválido")
    out = sorted(docs.values(), key=lambda d: (d["date"], d["reference"]))
    for d in out:
        for k in ("base", "vat", "deductible"):
            if k in d:
                d[k] = _money(d[k])
    return out
