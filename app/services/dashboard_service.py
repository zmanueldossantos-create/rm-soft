"""
Dashboard aggregation service - summary stats for the company's main
screen (revenue, invoice status breakdown, low stock alerts, recent sales).
"""
import uuid
from datetime import date
from calendar import monthrange

from sqlalchemy import case, literal, select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus, InvoiceType
from app.models.document_type import DocumentType
from app.services.document_rules import DOC_CODE_BY_INVOICE_TYPE
from app.models.stock import Stock
from app.models.product import Product
from app.models.customer import Customer


async def _document_signs(db: AsyncSession) -> dict:
    """{InvoiceType: +1 / -1} for the documents that count as sales (a credit note counts against)."""
    rows = (await db.execute(select(DocumentType.code, DocumentType.revenue_sign))).all()
    by_code = {code: sign for code, sign in rows}
    return {InvoiceType(stored): by_code.get(code) for stored, code in DOC_CODE_BY_INVOICE_TYPE.items() if by_code.get(code)}


def _signed(column, signs: dict):
    """column with the sign of its document (sale +, credit note -)."""
    return case(*[(Invoice.invoice_type == t, column * sign) for t, sign in signs.items()], else_=0) if signs else literal(0)


async def _document_behaviour(db: AsyncSession):
    """From the document type catalog: the signed total (sale +, credit note -, the others not counted), the invoice
    types that count as sales, and those sent to the AGT (the only ones that have a submission status)."""
    rows = (await db.execute(select(DocumentType.code, DocumentType.revenue_sign, DocumentType.sent_to_agt))).all()
    by_code = {code: (sign, sent) for code, sign, sent in rows}
    branches, sales_types, agt_types = [], [], []
    for stored, code in DOC_CODE_BY_INVOICE_TYPE.items():
        sign, sent = by_code.get(code, (0, False))
        member = InvoiceType(stored)
        if sign:
            branches.append((Invoice.invoice_type == member, Invoice.total * sign))
            sales_types.append(member)
        if sent:
            agt_types.append(member)
    signed_total = case(*branches, else_=0) if branches else literal(0)
    return signed_total, sales_types, agt_types


async def get_dashboard_summary(db: AsyncSession, company_id: uuid.UUID, permissions: set[str] | None = None) -> dict:
    """The gestor's Painel. Each block only for who may see what it is about (permissions): sales for every
    dashboard user, the money owed for who sees the invoices / purchases, the tills for the Tesouraria, the stock
    and its expiry dates for the stock, the day's production for the production."""
    permissions = permissions if permissions is not None else set()
    today = date.today()
    signed_total, sales_types, agt_types = await _document_behaviour(db)
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])

    # Revenue today
    revenue_today_result = await db.execute(
        select(func.coalesce(func.sum(signed_total), 0)).where(
            Invoice.company_id == company_id, Invoice.business_date == today,
            Invoice.invoice_type.in_(sales_types),
        )
    )
    revenue_today = float(revenue_today_result.scalar())

    # Revenue this month
    revenue_month_result = await db.execute(
        select(func.coalesce(func.sum(signed_total), 0)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
            Invoice.invoice_type.in_(sales_types),
        )
    )
    revenue_month = float(revenue_month_result.scalar())

    # Invoice count this month
    invoice_count_result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
            Invoice.invoice_type.in_(sales_types),
        )
    )
    invoice_count_month = invoice_count_result.scalar()

    # Invoices grouped by status (this month)
    status_result = await db.execute(
        select(Invoice.status, func.count(Invoice.id)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
            Invoice.invoice_type.in_(agt_types),  # only documents sent to the AGT have a submission status
            Invoice.issuance_mode == "ELETRONICA",  # a MANUAL document is declared by the SAF-T, never sent
        ).group_by(Invoice.status)
    )
    status_counts = {status.value: 0 for status in InvoiceStatus}
    for status, count in status_result.all():
        status_counts[status.value] = count

    # Low stock: one row per product, with each warehouse where it is at or under its minimum (the threshold is per
    # warehouse, as on the Stock screen) - the unit, and whether it is a raw material (the screen can hide those)
    from app.models.warehouse import Warehouse
    from app.models.unit_of_measure_catalog import UnitOfMeasureCatalog
    low_rows = (await db.execute(
        select(Product.id, Product.code, Product.name, Product.is_raw_material, UnitOfMeasureCatalog.code,
               Warehouse.name, Stock.quantity, Product.min_stock_threshold)
        .join(Stock, Stock.product_id == Product.id)
        .join(Warehouse, Warehouse.id == Stock.warehouse_id)
        .outerjoin(UnitOfMeasureCatalog, UnitOfMeasureCatalog.id == Product.unit_of_measure_id)
        .where(Product.company_id == company_id, Product.is_active.is_(True), Product.managed_by_stock.is_(True),
               Warehouse.is_active.is_(True), Product.min_stock_threshold > 0,  # a minimum of 0: no alert wanted
               Stock.quantity <= Product.min_stock_threshold)
        .order_by(Product.name, Warehouse.name)
    )).all() if "stock:view" in permissions else []
    low_by_product: dict = {}
    for pid, code, name, raw, unit, warehouse, qty, threshold in low_rows:
        row = low_by_product.setdefault(pid, {"code": code, "name": name, "is_raw_material": bool(raw), "unit_code": unit,
                                              "min_stock_threshold": float(threshold), "warehouses": []})
        row["warehouses"].append({"name": warehouse, "quantity": float(qty)})
    low_stock_products = list(low_by_product.values())

    # Recent invoices (last 8)
    recent_result = await db.execute(
        select(Invoice, Customer.name)
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.company_id == company_id, Invoice.invoice_type.in_(sales_types))  # never a pro-forma / quote
        .order_by(Invoice.created_at.desc())
        .limit(8)
    )
    recent_invoices = [
        {
            "id": str(inv.id),
            "series": inv.series,
            "number": inv.number,
            "invoice_type": inv.invoice_type.value,
            "total": float(inv.total),
            "status": inv.status.value,
            "business_date": inv.business_date.isoformat(),
            "customer_name": customer_name,
        }
        for inv, customer_name in recent_result.all()
    ]

    extra = await _extra_blocks(db, company_id, permissions, today, sales_types, signed_total)

    from app.models.company import Company
    company = await db.get(Company, company_id)
    mode = company.issuance_mode if company is not None else None
    electronic = (mode.value if hasattr(mode, "value") else mode) == "ELETRONICA"
    from app.services.agt_contingency import status as agt_status
    return {
        # Faturação Eletrónica: the link to the AGT, the contingência, what waits and what is late
        "agt": await agt_status(db, company) if electronic else None,
        # Faturação Eletrónica: the documents are sent to the AGT in real time (their states below mean something)
        "agt_realtime": (mode.value if hasattr(mode, "value") else mode) == "ELETRONICA",
        "revenue_today": revenue_today,
        "revenue_month": revenue_month,
        "invoice_count_month": invoice_count_month,
        "invoices_by_status": status_counts,
        "low_stock_products": low_stock_products,
        "recent_invoices": recent_invoices,
        **extra,
    }


async def _extra_blocks(db: AsyncSession, company_id: uuid.UUID, permissions: set[str], today: date, sales_types,
                        signed_total) -> dict:
    """The Painel beyond the totals: yesterday (to compare), the 30 days, what was received today by payment method,
    the best-selling products, the money owed both ways, the tills, the expiry dates and the day's production."""
    from datetime import timedelta
    from app.models.invoice_line import InvoiceLine
    from app.models.payment import Payment
    from app.models.payment_method_catalog import PaymentMethodCatalog
    signs = await _document_signs(db)
    month_start = date(today.year, today.month, 1)

    yesterday = today - timedelta(days=1)
    revenue_yesterday = float((await db.execute(select(func.coalesce(func.sum(signed_total), 0)).where(
        Invoice.company_id == company_id, Invoice.business_date == yesterday, Invoice.invoice_type.in_(sales_types),
    ))).scalar())

    # the last 30 days, one value per day (a day without sales is 0)
    start = today - timedelta(days=29)
    by_day = dict((await db.execute(
        select(Invoice.business_date, func.coalesce(func.sum(signed_total), 0))
        .where(Invoice.company_id == company_id, Invoice.business_date >= start, Invoice.business_date <= today,
               Invoice.invoice_type.in_(sales_types))
        .group_by(Invoice.business_date)
    )).all())
    sales_30_days = [{"date": (start + timedelta(days=i)).isoformat(), "total": float(by_day.get(start + timedelta(days=i), 0))}
                     for i in range(30)]

    # received today, by payment method (sales paid on the spot and receipts; a credit note's refund counts against)
    payments_today = [
        {"method": name, "is_cash": bool(is_cash), "amount": float(amount)}
        for name, is_cash, amount in (await db.execute(
            select(PaymentMethodCatalog.name, PaymentMethodCatalog.is_cash, func.sum(Payment.amount))
            .join(Payment, Payment.payment_method_id == PaymentMethodCatalog.id)
            .join(Invoice, Invoice.id == Payment.invoice_id)
            .where(Invoice.company_id == company_id, Invoice.business_date == today)
            .group_by(PaymentMethodCatalog.name, PaymentMethodCatalog.is_cash)
            .order_by(func.sum(Payment.amount).desc())
        )).all() if float(amount or 0) != 0
    ]

    async def top_products(since: date) -> list[dict]:
        rows = (await db.execute(
            select(InvoiceLine.product_name_snapshot, InvoiceLine.unit_code_snapshot,
                   func.sum(_signed(InvoiceLine.quantity * InvoiceLine.unit_factor, signs)),
                   func.sum(_signed(InvoiceLine.line_total, signs)))
            .join(Invoice, Invoice.id == InvoiceLine.invoice_id)
            .where(Invoice.company_id == company_id, Invoice.business_date >= since, Invoice.business_date <= today,
                   Invoice.invoice_type.in_(sales_types))
            .group_by(InvoiceLine.product_name_snapshot, InvoiceLine.unit_code_snapshot)
            .order_by(func.sum(_signed(InvoiceLine.line_total, signs)).desc())
            .limit(5)
        )).all()
        return [{"name": n, "unit_code": u, "quantity": float(q or 0), "total": float(t or 0)} for n, u, q, t in rows if float(t or 0) > 0]

    blocks = {
        "revenue_yesterday": revenue_yesterday,
        "sales_30_days": sales_30_days,
        "payments_today": payments_today,
        "top_products_today": await top_products(today),
        "top_products_month": await top_products(month_start),
    }

    if "invoices:view" in permissions:  # what the customers still owe (Faturas not yet paid by a receipt)
        from app.services.invoice_service import attach_amount_due
        owed = (await db.execute(select(Invoice).where(
            Invoice.company_id == company_id, Invoice.invoice_type.in_([InvoiceType.FACTURA, InvoiceType.NOTA_DEBITO]),
        ))).scalars().all()
        await attach_amount_due(db, list(owed))
        due = [inv for inv in owed if getattr(inv, "amount_due", 0) > 0.005]
        blocks["receivables"] = {
            "total": round(sum(inv.amount_due for inv in due), 2), "count": len(due),
            "overdue": round(sum(inv.amount_due for inv in due if inv.due_date and inv.due_date < today), 2),
        }

    if "purchases:view" in permissions:  # what the company still owes its suppliers
        from app.models.purchase_invoice import PurchaseInvoice, PurchaseInvoiceStatus
        from app.services.supplier_payment_service import invoice_balances
        bought = (await db.execute(select(PurchaseInvoice).where(
            PurchaseInvoice.company_id == company_id, PurchaseInvoice.status == PurchaseInvoiceStatus.REGISTADA,
            PurchaseInvoice.purchase_type == "FT"))).scalars().all()
        balances = await invoice_balances(db, bought)
        owing = [(inv, balances[inv.id]["due"]) for inv in bought if balances[inv.id]["due"] > 0.005]
        blocks["payables"] = {
            "total": round(sum(d for _, d in owing), 2), "count": len(owing),
            "overdue": round(sum(d for inv, d in owing if inv.due_date and inv.due_date < today), 2),
        }

    if "tesouraria:overview" in permissions:  # each till: open (who, since when, the cash it should hold) or its last closing
        from app.models.cash_session import CashSession, CashSessionStatus
        from app.models.point_of_sale import PointOfSale
        from app.models.user import User
        from app.services.cash_session_service import get_current_expected_cash_balance
        tills = []
        for pos in (await db.execute(select(PointOfSale).where(
                PointOfSale.company_id == company_id, PointOfSale.is_active.is_(True)).order_by(PointOfSale.name))).scalars().all():
            session = (await db.execute(select(CashSession).where(CashSession.pos_id == pos.id)
                                        .order_by(CashSession.opened_at.desc()).limit(1))).scalar_one_or_none()
            if session is None:
                continue  # never used
            opened_by = await db.get(User, session.opened_by_user_id)
            open_now = session.status == CashSessionStatus.ABERTA
            tills.append({
                "name": pos.name, "open": open_now, "user": opened_by.full_name if opened_by else None,
                "opened_at": session.opened_at.isoformat() if session.opened_at else None,
                "cash": await get_current_expected_cash_balance(db, company_id, pos.id, session) if open_now
                else float(session.closing_amount_counted or 0),
                "closed_at": session.closed_at.isoformat() if session.closed_at else None,
                "difference": None if open_now or session.closing_difference is None else float(session.closing_difference),
            })
        blocks["tills"] = tills

    if "stock:view" in permissions:  # the lots that expire soon (or have expired), first to go
        from app.services.stock_lot_service import list_expiring
        expiring = await list_expiring(db, company_id, today=today)
        blocks["expiring"] = {
            "alert_days": expiring["alert_days"], "expired_count": expiring["expired_count"],
            "expiring_count": expiring["expiring_count"],
            "lots": [{"product_name": l["product_name"], "warehouse_name": l["warehouse_name"], "quantity": l["quantity"],
                      "unit_code": l["unit_code"], "expiry_date": l["expiry_date"].isoformat(), "days_left": l["days_left"],
                      "expired": l["expired"]} for l in expiring["lots"][:6]],
        }

    if "production:view" in permissions or "recipes:view" in permissions:  # what was made today and its cost
        from app.services.stock_service import list_production_history
        batches = await list_production_history(db, company_id, date_from=today.isoformat(), date_to=today.isoformat())
        made = [b["output"] for b in batches if b["output"]]
        blocks["production_today"] = {
            "count": len(made),
            "cost": round(sum(o["unit_cost"] * o["quantity"] for o in made if o["unit_cost"] is not None), 2),
            "items": [{"name": o["product_name"], "quantity": o["quantity"], "unit_code": o.get("unit_code")} for o in made[:6]],
        }
    return blocks
