"""
SAF-T export service - gathers a company's data for a given fiscal period
(year/month) and generates the AuditFile XML. See specification v6/v7,
section 4.2 "Modo Fatura" - exported at month end, submitted manually to
the AGT portal by the business.
"""
import uuid
from datetime import date
from calendar import monthrange

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.company import Company
from app.models.customer import Customer
from app.models.product import Product
from app.models.vat import VAT
from app.models.invoice import Invoice
from app.models.invoice_line import InvoiceLine
from app.models.platform_settings import PlatformSettings
from app.utils.saf_t_generator import generate_saf_t_xml


class CompanyNotFoundError(Exception):
    pass


async def export_saf_t_for_period(db: AsyncSession, company_id: uuid.UUID, year: int, month: int) -> bytes:
    """Generates the SAF-T AuditFile XML for one calendar month."""
    company_result = await db.execute(select(Company).where(Company.id == company_id))
    company = company_result.scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError("Empresa nao encontrada")

    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])

    customers_result = await db.execute(select(Customer).where(Customer.company_id == company_id))
    customers = customers_result.scalars().all()

    products_result = await db.execute(select(Product).where(Product.company_id == company_id))
    products = products_result.scalars().all()

    vat_result = await db.execute(select(VAT).where(VAT.company_id == company_id))
    vat_rates = vat_result.scalars().all()

    invoices_result = await db.execute(
        select(Invoice).where(
            Invoice.company_id == company_id,
            Invoice.business_date >= start_date,
            Invoice.business_date <= end_date,
        )
    )
    invoices = invoices_result.scalars().all()

    settings_result = await db.execute(select(PlatformSettings).limit(1))
    platform_settings = settings_result.scalar_one_or_none()

    invoices_data = []
    for inv in invoices:
        lines_result = await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == inv.id))
        lines = lines_result.scalars().all()

        invoices_data.append({
            "invoice_type": inv.invoice_type.value,
            "series": inv.series,
            "number": inv.number,
            "number_digits": inv.number_digits,
            "business_date": inv.business_date,
            "created_at": inv.created_at.replace(tzinfo=None),
            "atcud": inv.atcud,
            "invoice_hash": inv.invoice_hash,
            "subtotal": float(inv.subtotal),
            "vat_total": float(inv.vat_total),
            "total": float(inv.total),
            "customer_id": str(inv.customer_id) if inv.customer_id else None,
            "lines": [
                {
                    "product_code": next((p.code for p in products if p.id == l.product_id), "N/A"),
                    "product_name": l.product_name_snapshot,
                    "quantity": float(l.quantity),
                    "unit_price": float(l.unit_price),
                    "vat_rate": float(l.vat_rate_snapshot),
                    "line_subtotal": float(l.line_subtotal),
                    "line_vat": float(l.line_vat),
                    "line_total": float(l.line_total),
                }
                for l in lines
            ],
        })

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
    vat_data = [{"name": v.name, "rate": float(v.rate)} for v in vat_rates]

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
    )
