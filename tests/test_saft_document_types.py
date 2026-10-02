"""
Tests for the SAF-T generator's handling of document types: only documents that map to a SAF-T InvoiceType
are exported as invoices (a pro-forma or a receipt used to fall through to "FT"), TotalDebit / TotalCredit are
the sums of the net DebitAmount / CreditAmount (XSD), and a credit note carries its lines as DebitAmount.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _invoice(invoice_type, number, subtotal, vat):
    total = subtotal + vat
    return {
        "invoice_type": invoice_type, "series": "S1", "number": number, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc",
        "subtotal": subtotal, "vat_total": vat, "total": total, "customer_id": None,
        "lines": [{
            "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": subtotal,
            "vat_rate": 14.0, "line_subtotal": subtotal, "line_vat": vat, "line_total": total,
        }],
    }


def _generate(invoices):
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0}],
        invoices=invoices, fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))


def test_only_documents_with_a_saft_invoice_type_are_exported_as_invoices():
    root = _generate([_invoice("FACTURA", 1, 1000.0, 140.0), _invoice("PRO_FORMA", 1, 500.0, 70.0), _invoice("RECIBO", 1, 200.0, 28.0)])
    invoices = root.findall(".//s:SalesInvoices/s:Invoice", NS)
    assert [i.findtext("s:InvoiceType", namespaces=NS) for i in invoices] == ["FT"]
    assert root.findtext(".//s:SalesInvoices/s:NumberOfEntries", namespaces=NS) == "1"


def test_totals_are_net_and_credit_notes_are_debits():
    root = _generate([
        _invoice("FACTURA", 1, 1000.0, 140.0), _invoice("FACTURA_RECIBO", 1, 2000.0, 280.0),
        _invoice("NOTA_CREDITO", 1, 500.0, 70.0), _invoice("NOTA_DEBITO", 1, 100.0, 14.0),
    ])
    assert root.findtext(".//s:SalesInvoices/s:TotalCredit", namespaces=NS) == "3100.00"  # FT + FR + ND, net of tax
    assert root.findtext(".//s:SalesInvoices/s:TotalDebit", namespaces=NS) == "500.00"    # the credit note
    amounts = {
        i.findtext("s:InvoiceType", namespaces=NS): [etree.QName(c).localname for c in i.find("s:Line", NS) if etree.QName(c).localname in ("DebitAmount", "CreditAmount")]
        for i in root.findall(".//s:SalesInvoices/s:Invoice", NS)
    }
    assert amounts == {"FT": ["CreditAmount"], "FR": ["CreditAmount"], "NC": ["DebitAmount"], "ND": ["CreditAmount"]}