"""Point 6: each SAF-T section lists its documents in their numbering order (type, series, number) - FR2026/2 before
FR2026/10 - whatever order they come in."""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _doc(invoice_type, number, series="FR2026"):
    return {
        "invoice_type": invoice_type, "series": series, "number": number,
        "business_date": date(2026, 10, 1), "created_at": datetime(2026, 10, 1, 10, 0, 0),
        "atcud": f"SIMUL-{number}", "invoice_hash": "SIMUL-abc", "subtotal": 100.0, "vat_total": 14.0, "total": 114.0,
        "customer_id": None,
        "lines": [{"product_code": "SRV-1", "product_name": "Serviço", "quantity": 1.0, "unit_price": 100.0, "vat_rate": 14.0,
                   "tax_code": "NOR", "unit_code": "UN", "line_subtotal": 100.0, "line_vat": 14.0, "line_total": 114.0}],
    }


def test_sales_invoices_are_listed_by_type_series_and_number():
    docs = [_doc("FACTURA_RECIBO", 10), _doc("FACTURA", 1, "FT2026"), _doc("FACTURA_RECIBO", 2), _doc("FACTURA_RECIBO", 1)]
    root = etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Serviço", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}],
        invoices=docs, fiscal_year=2026, start_date=date(2026, 10, 1), end_date=date(2026, 10, 31),
    ))
    numbers = [i.findtext("s:InvoiceNo", namespaces=NS) for i in root.findall(".//s:SalesInvoices/s:Invoice", NS)]
    assert numbers == ["FR FR2026/1", "FR FR2026/2", "FR FR2026/10", "FT FT2026/1"]
