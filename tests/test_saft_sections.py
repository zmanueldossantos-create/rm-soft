"""The SAF-T section of a document (Faturas / Payments / Working) comes from the document type catalog."""
import pytest
from lxml import etree
from sqlalchemy import text

from app.models.service import Service
from app.services.invoice_service import create_invoice, create_pro_forma, create_receipt
from app.services.saf_t_export_service import export_saf_t_for_period

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_export_follows_the_saft_section_rule(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-SC", name="Servico SC", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]

    ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
    ft_id, year, month = ft.id, ft.business_date.year, ft.business_date.month
    await create_pro_forma(db, company_id, activity_id, None, lines)
    await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=100.0)

    async def counts():
        root = etree.fromstring(await export_saf_t_for_period(db, company_id, year, month))
        return tuple(root.findtext(f".//s:{name}/s:NumberOfEntries", namespaces=NS) for name in ("SalesInvoices", "WorkingDocuments", "Payments"))

    assert await counts() == ("1", "1", "1")
    try:
        await _set_rule(db, "FT", saft_section="NONE")
        assert (await counts())[0] == "0"  # a document with no SAF-T section is not exported
    finally:
        await _set_rule(db, "FT", saft_section="INVOICES")