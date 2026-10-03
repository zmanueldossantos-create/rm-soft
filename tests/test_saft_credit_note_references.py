"""
XSD: the lines of a credit note carry References (mandatory for an NC): the credited document, in the numbering of
its own InvoiceNo, and the reason - limited to 50 characters in the SAF-T. Other documents carry none.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _invoice(invoice_type, subtotal, vat):
    total = subtotal + vat
    return {
        "invoice_type": invoice_type, "series": "S1", "number": 1, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc",
        "subtotal": subtotal, "vat_total": vat, "total": total, "customer_id": None,
        "lines": [{
            "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": subtotal,
            "vat_rate": 14.0, "tax_code": "NOR", "line_subtotal": subtotal, "line_vat": vat, "line_total": total,
        }],
    }


def test_credit_note_lines_reference_the_credited_document_and_its_reason():
    credit_note = _invoice("NOTA_CREDITO", 500.0, 70.0)
    credit_note["document_reference"] = "FT FT1S1N/1"
    credit_note["credit_note_cause"] = "x" * 60
    root = etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}],
        invoices=[_invoice("FACTURA", 1000.0, 140.0), credit_note],
        fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))
    lines = {i.findtext("s:InvoiceType", namespaces=NS): i.find("s:Line", NS) for i in root.findall(".//s:SalesInvoices/s:Invoice", NS)}

    names = [etree.QName(c).localname for c in lines["NC"]]
    assert names.index("References") == names.index("TaxPointDate") + 1  # position required by the XSD
    references = lines["NC"].find("s:References", NS)
    assert references.findtext("s:Reference", namespaces=NS) == "FT FT1S1N/1"
    assert references.findtext("s:Reason", namespaces=NS) == "x" * 50  # truncated to the XSD limit
    assert lines["FT"].find("s:References", NS) is None