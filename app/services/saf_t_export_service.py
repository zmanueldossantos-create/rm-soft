"""
SAF-T export service - gathers a company's data for a given fiscal period
(year/month) and generates the AuditFile XML. See specification v6/v7,
section 4.2 "Modo Fatura" - exported at month end, submitted manually to
the AGT portal by the business.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

LUANDA = timezone(timedelta(hours=1))  # Angola: UTC+1 all year


def _local(moment: datetime) -> datetime:
    """A recorded moment in Luanda time, without offset - the SAF-T dates (SystemEntryDate, InvoiceStatusDate)
    are local times: a sale at 00h30 in Luanda belongs to that day, not the previous one."""
    return (moment.astimezone(LUANDA) if moment.tzinfo else moment).replace(tzinfo=None)
from calendar import monthrange

from sqlalchemy import select, text
from app.models.document_type import DocumentType
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.customer import Customer
from app.models.product import Product
from app.models.service import Service
from app.models.vat import VAT
from app.models.invoice import Invoice
from app.services.document_amounts import split_global_discount
from app.models.user import User
from app.models.invoice_line import InvoiceLine
from app.models.platform_settings import PlatformSettings
from app.utils.saf_t_generator import INVOICE_TYPE_MAP, generate_saf_t_xml


def _apply_declared_amounts(doc: dict, discount_percent: float) -> None:
    """
    The amounts the SAF-T declares, as the AGT specification defines them: each line's amount after ALL its discounts,
    its SettlementAmount = its own discount + its share of the global discount, and the document's NetTotal and
    TaxPayable after the global discount (the stored subtotal and VAT are before it; the stored total, after).
    A receipt declares a payment, not sale lines: left as it is.
    """
    if doc.get("invoice_type") == "RECIBO":
        return
    for line in doc["lines"]:
        gross = round(line["quantity"] * line["unit_price"], 2)
        line["settlement"] = max(round(gross - line["line_subtotal"], 2), 0.0)  # the line's own discount
    if not discount_percent:
        return
    split = split_global_discount([(l["line_subtotal"], l["vat_rate"]) for l in doc["lines"]], discount_percent, doc["total"])
    for line, part in zip(doc["lines"], split["lines"]):
        line["line_subtotal"] = part["net"]
        line["settlement"] = round(line["settlement"] + part["settlement"], 2)
    doc["subtotal"], doc["vat_total"] = split["net_total"], split["tax_total"]


class CompanyNotFoundError(Exception):
    pass


async def _receipt_extras(db: AsyncSession, receipt: Invoice) -> dict:
    """What the SAF-T Payments section needs about a receipt: the invoice it settles (its InvoiceNo and date), the
    cash by payment method, and the withholding - by type - the receipt settles (the settled share of the invoice's)."""
    extras: dict = {"reference_invoice_no": None, "reference_invoice_date": None, "payment_methods": [], "withholding": []}
    ref = None
    if receipt.reference_invoice_id is not None:
        ref = (await db.execute(select(Invoice).where(Invoice.id == receipt.reference_invoice_id))).scalar_one_or_none()
    if ref is not None:
        extras["reference_invoice_no"] = f"{INVOICE_TYPE_MAP.get(ref.invoice_type.value, 'FT')} {ref.series}/{ref.number}"
        extras["reference_invoice_date"] = ref.business_date
    rows = (await db.execute(
        text("SELECT pm.code, p.amount FROM payments p JOIN payment_method_catalog pm ON pm.id = p.payment_method_id WHERE p.invoice_id = :id"),
        {"id": receipt.id},
    )).all()
    extras["payment_methods"] = [{"code": code, "amount": float(amount)} for code, amount in rows]
    if ref is not None and float(receipt.retention_total or 0) > 0 and float(ref.retention_total or 0) > 0:
        share = float(receipt.retention_total) / float(ref.retention_total)
        by_type: dict[str, dict] = {}
        for line in (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == ref.id))).scalars().all():
            if line.retention_amount:
                entry = by_type.setdefault(line.retention_type or "OU", {"amount": 0.0, "name": line.retention_name_snapshot})
                entry["amount"] += float(line.retention_amount)
        withholding = [{"type": k, "name": v["name"], "amount": round(v["amount"] * share, 2)} for k, v in by_type.items()]
        difference = round(float(receipt.retention_total) - sum(w["amount"] for w in withholding), 2)
        if withholding and difference:  # rounding: the entries must add up to the receipt's own withholding
            withholding[0]["amount"] = round(withholding[0]["amount"] + difference, 2)
        extras["withholding"] = withholding
    return extras


async def _purchases_for_saft(db: AsyncSession, company_id: uuid.UUID, year: int, month: int, source_codes: dict) -> tuple[list, list]:
    """
    The purchase invoices booked in the month (REGISTADA - a cancelled registration is not declared) and their
    suppliers, for the SAF-T PurchaseInvoices: each document with its totals and its deductible VAT by destination.
    """
    from app.models.country import Country
    from app.models.fiscal_period import FiscalPeriod
    from app.models.fiscal_year import FiscalYear
    from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceLine, PurchaseInvoiceStatus
    from app.models.supplier import Supplier
    invoices = (await db.execute(
        select(PurchaseInvoice).join(FiscalPeriod, FiscalPeriod.id == PurchaseInvoice.fiscal_period_id)
        .join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id)
        .where(PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
               FiscalYear.year == year, FiscalPeriod.month == month)
        .order_by(PurchaseInvoice.series, PurchaseInvoice.number)
    )).scalars().all()
    if not invoices:
        return [], []
    lines = (await db.execute(select(PurchaseInvoiceLine).where(
        PurchaseInvoiceLine.purchase_invoice_id.in_([i.id for i in invoices])))).scalars().all()
    references = {i.id: i for i in (await db.execute(select(PurchaseInvoice).where(
        PurchaseInvoice.id.in_([i.reference_invoice_id for i in invoices if i.reference_invoice_id])))).scalars().all()}
    supplier_rows = (await db.execute(
        select(Supplier, Country.code).outerjoin(Country, Country.id == Supplier.country_id)
        .where(Supplier.id.in_({i.supplier_id for i in invoices})).order_by(Supplier.name, Supplier.id)
    )).all()
    suppliers = [{"id": sup.id, "name": sup.name, "nif": sup.nif, "address": sup.address, "phone_number": sup.phone_number,
                  "email": sup.email, "country": (country or "AO").upper()} for sup, country in supplier_rows]
    purchases = []
    for inv in invoices:
        deductible: dict[str, dict] = {}
        for line in (l for l in lines if l.purchase_invoice_id == inv.id):
            group = deductible.setdefault(line.deductible_tax_type, {"base": 0.0, "amount": 0.0})
            group["base"] += float(line.line_subtotal)
            group["amount"] += float(line.vat_deductible)
        ref = references.get(inv.reference_invoice_id)
        purchases.append({
            "invoice_no": inv.supplier_document, "hash": inv.supplier_hash or "0", "purchase_type": inv.purchase_type,
            "invoice_date": inv.document_date, "period": month, "supplier_id": inv.supplier_id,
            "source_id": (source_codes.get(inv.created_by_user_id) or "RMSOFT")[:30],
            "vat_total": float(inv.vat_total), "subtotal": float(inv.subtotal), "total": float(inv.total),
            "deductible_pct": float(inv.deductible_pct),
            "deductible": [{"type": t, "base": g["base"], "amount": g["amount"]} for t, g in sorted(deductible.items())],
            "reference": {"no": ref.supplier_document, "date": ref.document_date} if ref else None,
        })
    return suppliers, purchases


async def _movements_for_saft(db: AsyncSession, company_id: uuid.UUID, start_date: date, end_date: date,
                              source_codes: dict) -> tuple[list, list]:
    """
    The guides issued in the month (MovementOfGoods) - the cancelled ones too, declared as such - and the suppliers of
    the GD (returns), which the MasterFiles must hold even when the purchases are not exported.
    """
    from app.models.country import Country
    from app.models.goods_movement import GoodsMovement, GoodsMovementLine, GoodsMovementStatus
    from app.models.supplier import Supplier
    movements = (await db.execute(select(GoodsMovement).where(
        GoodsMovement.company_id == company_id, GoodsMovement.movement_date >= start_date,
        GoodsMovement.movement_date <= end_date))).scalars().all()
    if not movements:
        return [], []
    lines = (await db.execute(select(GoodsMovementLine).where(
        GoodsMovementLine.goods_movement_id.in_([m.id for m in movements]))
        .order_by(GoodsMovementLine.position))).scalars().all()
    invoiced_at = dict((await db.execute(select(Invoice.id, Invoice.created_at).where(
        Invoice.id.in_([m.invoice_id for m in movements if m.invoice_id])))).all()) if any(m.invoice_id for m in movements) else {}
    supplier_rows = (await db.execute(
        select(Supplier, Country.code).outerjoin(Country, Country.id == Supplier.country_id)
        .where(Supplier.id.in_({m.supplier_id for m in movements if m.supplier_id})).order_by(Supplier.name, Supplier.id)
    )).all()
    suppliers = [{"id": sup.id, "name": sup.name, "nif": sup.nif, "address": sup.address, "phone_number": sup.phone_number,
                  "email": sup.email, "country": (country or "AO").upper()} for sup, country in supplier_rows]
    status_code = {GoodsMovementStatus.EMITIDA: "N", GoodsMovementStatus.FATURADA: "F", GoodsMovementStatus.ANULADA: "A"}
    data = []
    for m in movements:
        # the date of the current state: issued, invoiced (the invoice's issue) or cancelled
        status_date = m.cancelled_at if m.status == GoodsMovementStatus.ANULADA else \
            invoiced_at.get(m.invoice_id, m.created_at) if m.status == GoodsMovementStatus.FATURADA else m.created_at
        data.append({
            "movement_type": m.movement_type, "series": m.series, "number": m.number, "status": status_code[m.status],
            "status_date": _local(status_date or m.created_at), "reason": m.cancel_reason,
            "source_id": (source_codes.get(m.created_by_user_id) or "RMSOFT")[:30], "hash": m.document_hash,
            "movement_date": m.movement_date, "system_entry_date": _local(m.created_at), "start_time": _local(m.start_time),
            "customer_id": str(m.customer_id) if m.customer_id else None, "supplier_id": m.supplier_id,
            "own_company": m.movement_type == "GT", "comments": m.notes, "load_address": m.load_address,
            "unload_address": m.unload_address, "net_total": float(m.net_total), "vat_total": float(m.vat_total),
            "gross_total": float(m.gross_total),
            "lines": [{
                "product_code": l.product_code, "description": l.description, "quantity": float(l.quantity),
                "unit_code": l.unit_code, "unit_price": float(l.unit_price), "line_net": float(l.line_net),
                "tax_code": l.tax_code, "vat_rate": float(l.vat_rate), "exemption_code": l.exemption_code,
                "exemption_reason": l.exemption_reason,
            } for l in lines if l.goods_movement_id == m.id],
        })
    return suppliers, data


async def export_saf_t_for_period(db: AsyncSession, company_id: uuid.UUID, year: int, month: int,
                                  include_purchases: bool = False) -> bytes:
    """
    Generates the SAF-T AuditFile XML for one calendar month. include_purchases (the company's choice on the export
    screen): the purchase invoices of the month and their suppliers too - the file is then of the type Q (acquisitions
    integrated with the invoicing) instead of F.
    """
    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError("Empresa não encontrada")

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    # Stable order: the SAF-T CustomerID is the position in this list, so it must not shift between exports.
    customers_result = await db.execute(
        select(Customer).where(Customer.company_id == company_id).order_by(Customer.created_at, Customer.id)
    )
    customers = customers_result.scalars().all()

    products_result = await db.execute(select(Product).where(Product.company_id == company_id).order_by(Product.code))
    products = products_result.scalars().all()

    # Services are sellable articles too: a service line has no product_id, so it used to be exported with
    # ProductCode "N/A" - which matches no MasterFiles/Product (XSD keyref InvoiceProductCodeConstraint) -
    # and the service itself never reached MasterFiles.
    services_result = await db.execute(select(Service).where(Service.company_id == company_id).order_by(Service.code))
    services = services_result.scalars().all()
    product_code_by_id = {p.id: p.code for p in products}
    service_code_by_id = {s.id: s.code for s in services}

    vat_result = await db.execute(select(VAT).where(VAT.company_id == company_id))
    vat_rates = vat_result.scalars().all()

    invoices_result = await db.execute(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= start_date,
            Invoice.business_date <= end_date,
        ).order_by(Invoice.invoice_type, Invoice.series, Invoice.number)  # the generator sorts each section too
    )
    invoices = invoices_result.scalars().all()

    settings_result = await db.execute(select(PlatformSettings).limit(1))
    platform_settings = settings_result.scalar_one_or_none()

    # SAF-T section of each document (Faturas / Payments / Working), from the document type catalog.
    section_by_code = {code: section for code, section in (await db.execute(select(DocumentType.code, DocumentType.saft_section))).all()}
    # SourceID - "Codigo do utilizador": the phone number the author logs in with (unique in the company, 13
    # characters of the 30 allowed). A document recorded before the author was kept falls back to RMSOFT.
    source_codes = dict((await db.execute(
        select(User.id, User.phone_number).where(User.company_id == company_id)
    )).all())
    invoices_data = []
    for inv in invoices:
        receipt_extra = await _receipt_extras(db, inv) if inv.invoice_type.value == "RECIBO" else {}
        lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id).order_by(InvoiceLine.created_at, InvoiceLine.id))
        lines = lines_result.scalars().all()

        invoices_data.append({
            "invoice_type": inv.invoice_type.value,
            "series": inv.series,
            "number": inv.number,
            "business_date": inv.business_date,
            "created_at": _local(inv.created_at),
            "atcud": inv.atcud,
            "invoice_hash": inv.invoice_hash,
            "source_id": (source_codes.get(inv.created_by_user_id) or "RMSOFT")[:30],
            "subtotal": float(inv.subtotal),
            "vat_total": float(inv.vat_total),
            "total": float(inv.total),
            "customer_id": str(inv.customer_id) if inv.customer_id else None,
            "document_reference": inv.document_reference,
            "credit_note_cause": inv.credit_note_cause,
            "converted": inv.converted_to_invoice_id is not None,
            **receipt_extra,
            "saft_section": section_by_code.get(DOC_CODE_BY_INVOICE_TYPE.get(inv.invoice_type.value, ""), "NONE"),
            "lines": [
                {
                    "product_code": product_code_by_id.get(l.product_id) or service_code_by_id.get(l.service_id) or "N/A",
                    "product_name": l.product_name_snapshot,
                    "quantity": float(l.quantity), "unit_code": l.unit_code_snapshot,
                    "unit_price": float(l.unit_price),
                    "vat_rate": float(l.vat_rate_snapshot), "tax_code": l.tax_code_snapshot,
                    "line_subtotal": float(l.line_subtotal),
                    "line_vat": float(l.line_vat),
                    "line_total": float(l.line_total),
                    "exemption_code": l.exemption_code, "exemption_reason": l.exemption_reason_snapshot,
                    "retention_type": l.retention_type,
                    "retention_name": l.retention_name_snapshot,
                    "retention_amount": float(l.retention_amount) if l.retention_amount is not None else None,
                    "goods_movement_id": l.goods_movement_id,
                }
                for l in lines
            ],
        })
        _apply_declared_amounts(invoices_data[-1], float(inv.discount_global_percent or 0))

    company_dict = {
        "name": company.name,
        "nif": company.nif,
        "address": company.address,
        "phone_number": company.phone_number,
        "email": company.email,
        "commercial_registration_number": company.commercial_registration_number,
    }
    platform_dict = {
        "software_validation_number": platform_settings.software_validation_number if platform_settings else None,
        "vendor_tax_id": platform_settings.vendor_tax_id if platform_settings else None,
        "product_id": platform_settings.product_id if platform_settings else None,
        "product_version": platform_settings.product_version if platform_settings else None,
    }
    customers_data = [
        {"id": str(c.id), "nif": c.nif, "name": c.name, "address": c.address, "phone_number": c.phone_number, "email": c.email}
        for c in customers
    ]
    products_data = [{"code": p.code, "name": p.name, "product_type": p.product_type.value} for p in products]
    known_codes = {d["code"] for d in products_data}
    products_data += [{"code": s.code, "name": s.name, "product_type": "SERVICO"} for s in services if s.code not in known_codes]
    products_data.sort(key=lambda d: d["code"])  # MasterFiles in code order, products and services together (as the AGT-validated exports)
    vat_data = [{"name": v.name, "rate": float(v.rate), "tax_code": v.tax_category} for v in vat_rates]

    # An invoice issued from a pro-forma names it (OrderReferences): the pro-forma keeps the link (converted_to_invoice_id).
    from sqlalchemy.orm import aliased as _aliased
    _fp, _ft = _aliased(Invoice), _aliased(Invoice)
    from app.utils.saf_t_generator import WORK_TYPE_MAP
    _origins = (await db.execute(
        select(_fp.invoice_type, _fp.series, _fp.number, _fp.business_date, _ft.series, _ft.number)
        .join(_ft, _ft.id == _fp.converted_to_invoice_id)
        .where(_fp.company_id == company_id)
    )).all()
    # the origin in its own SAF-T numbering: PP FP2026/3 (a pro-forma), OR OR2026/1 (an orçamento)
    _origin_by_doc = {(fs, fn): (f"{WORK_TYPE_MAP.get(pt.value, 'PP')} {ps}/{pn}", pd) for pt, ps, pn, pd, fs, fn in _origins}
    for _doc in invoices_data:
        _origin = _origin_by_doc.get((_doc.get("series"), _doc.get("number")))
        if _origin:
            _doc["order_reference"], _doc["order_date"] = _origin
    # A line invoiced from a guia de remessa names its GR (OrderReferences: GR GR2026/2 and its date)
    from app.models.goods_movement import GoodsMovement
    guide_ids = {l["goods_movement_id"] for d in invoices_data for l in d["lines"] if l.get("goods_movement_id")}
    guides = {g.id: g for g in (await db.execute(select(GoodsMovement).where(GoodsMovement.id.in_(guide_ids)))).scalars().all()} \
        if guide_ids else {}
    for _doc in invoices_data:
        for _line in _doc["lines"]:
            guide = guides.get(_line.pop("goods_movement_id", None))
            if guide is not None:
                _line["order_reference"] = f"{guide.movement_type} {guide.series}/{guide.number}"
                _line["order_date"] = guide.movement_date
    suppliers_data, purchases_data = (await _purchases_for_saft(db, company_id, year, month, source_codes)) \
        if include_purchases else ([], None)
    # The guides of the month; the suppliers of their returns join the MasterFiles (once)
    movement_suppliers, movements_data = await _movements_for_saft(db, company_id, start_date, end_date, source_codes)
    known_suppliers = {sup["id"] for sup in suppliers_data}
    suppliers_data = suppliers_data + [sup for sup in movement_suppliers if sup["id"] not in known_suppliers]
    return generate_saf_t_xml(
        company=company_dict,
        platform_settings=platform_dict,
        customers=customers_data,
        products=products_data,
        vat_rates=vat_data,
        invoices=invoices_data,
        fiscal_year=year,
        start_date=start_date,
        end_date=end_date,
        suppliers=suppliers_data,
        purchases=purchases_data,
        movements=movements_data,
    )
