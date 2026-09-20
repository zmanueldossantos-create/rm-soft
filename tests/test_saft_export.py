"""
Tests for the SAF-T export of a service invoice: the service is exported in MasterFiles/Product (type S),
its invoice line carries the service code (never "N/A", which matches no MasterFiles product - XSD keyref
InvoiceProductCodeConstraint) and the document number has no leading zeros.
"""
import re

import pytest
from lxml import etree

from app.models.service import Service
from app.services.invoice_service import create_invoice
from app.services.saf_t_export_service import export_saf_t_for_period

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


@pytest.mark.asyncio
async def test_service_invoice_export_lists_the_service_and_numbers_without_zeros(db, company_with_essentials):
    setup = company_with_essentials
    company = setup["company"]
    service = Service(company_id=company.id, code="SRV-SAFT", name="Servico SAF-T", price=500.0, vat_id=setup["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)

    invoice = await create_invoice(
        db, company.id, setup["activity"].id, customer_id=None,
        invoice_type="FACTURA", lines_input=[{"service_id": service.id, "quantity": 1}],
    )
    xml = await export_saf_t_for_period(db, company.id, invoice.business_date.year, invoice.business_date.month)
    root = etree.fromstring(xml)

    products = {
        p.findtext("s:ProductCode", namespaces=NS): p.findtext("s:ProductType", namespaces=NS)
        for p in root.findall(".//s:MasterFiles/s:Product", NS)
    }
    assert products.get("SRV-SAFT") == "S"

    line_codes = [l.findtext("s:ProductCode", namespaces=NS) for l in root.findall(".//s:SalesInvoices/s:Invoice/s:Line", NS)]
    assert line_codes == ["SRV-SAFT"]
    assert set(line_codes) <= set(products)  # every line references a MasterFiles product

    invoice_no = root.findtext(".//s:SalesInvoices/s:Invoice/s:InvoiceNo", namespaces=NS)
    assert re.fullmatch(r"FT \S+/[1-9]\d*", invoice_no), invoice_no