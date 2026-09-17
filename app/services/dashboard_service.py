"""
Dashboard aggregation service - summary stats for the company's main
screen (revenue, invoice status breakdown, low stock alerts, recent sales).
"""
import uuid
from datetime import date
from calendar import monthrange

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invoice import Invoice, InvoiceStatus
from app.models.stock import Stock
from app.models.product import Product
from app.models.customer import Customer


async def get_dashboard_summary(db: AsyncSession, company_id: uuid.UUID) -> dict:
    today = date.today()
    month_start = date(today.year, today.month, 1)
    month_end = date(today.year, today.month, monthrange(today.year, today.month)[1])

    # Revenue today
    revenue_today_result = await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.company_id == company_id, Invoice.business_date == today
        )
    )
    revenue_today = float(revenue_today_result.scalar())

    # Revenue this month
    revenue_month_result = await db.execute(
        select(func.coalesce(func.sum(Invoice.total), 0)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
        )
    )
    revenue_month = float(revenue_month_result.scalar())

    # Invoice count this month
    invoice_count_result = await db.execute(
        select(func.count(Invoice.id)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
        )
    )
    invoice_count_month = invoice_count_result.scalar()

    # Invoices grouped by status (this month)
    status_result = await db.execute(
        select(Invoice.status, func.count(Invoice.id)).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= month_start,
            Invoice.business_date <= month_end,
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
