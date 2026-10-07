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


async def get_dashboard_summary(db: AsyncSession, company_id: uuid.UUID) -> dict:
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
        ).group_by(Invoice.status)
    )
    status_counts = {status.value: 0 for status in InvoiceStatus}
    for status, count in status_result.all():
        status_counts[status.value] = count

    # Low stock products
    low_stock_result = await db.execute(
        select(Product.code, Product.name, Stock.quantity, Product.min_stock_threshold)
        .join(Stock, Stock.product_id == Product.id)
        .where(
            Product.company_id == company_id,
            Product.is_active == True,
            Stock.quantity <= Product.min_stock_threshold,
        )
        .order_by(Product.name)
    )
    low_stock_products = [
        {"code": code, "name": name, "quantity": float(qty), "min_stock_threshold": float(threshold)}
        for code, name, qty, threshold in low_stock_result.all()
    ]

    # Recent invoices (last 8)
    recent_result = await db.execute(
        select(Invoice, Customer.name)
        .outerjoin(Customer, Customer.id == Invoice.customer_id)
        .where(Invoice.company_id == company_id)
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

    return {
        "revenue_today": revenue_today,
        "revenue_month": revenue_month,
        "invoice_count_month": invoice_count_month,
        "invoices_by_status": status_counts,
        "low_stock_products": low_stock_products,
        "recent_invoices": recent_invoices,
    }
