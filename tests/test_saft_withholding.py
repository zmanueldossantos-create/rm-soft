"""
XSD: the withholding of a document is reported after DocumentTotals as WithholdingTax - one entry per type (II, IPU...),
amounts summed over the lines, description limited to 60 characters; a withholding without a known type is "OU".
A document without withholding carries none.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}
II_NAME = "Reten\u00e7\u00e3o na fonte(6,5)"


def _line(retention_type=None, retention_amount=None, name=None):
    return {
        "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": 1000.0, "vat_rate": 14.0,
        "line_subtotal": 1000.0, "line_vat": 140.0, "line_total": 1140.0,
        "retention_type": retention_type, "retention_name": name, "retention_amount": retention_amount,
    }


def _generate(lines):
    doc = {
        "invoice_type": "FACTURA", "series": "S1", "number": 1, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc", "subtotal": 1000.0 * len(lines), "vat_total": 140.0 * len(lines),
        "total": 1140.0 * len(lines), "customer_id": None, "lines": lines,
    }
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0}],
        invoices=[doc], fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))


def test_withholding_is_reported_per_type_after_the_document_totals():
    root = _generate([
        _line("II", 65.0, II_NAME), _line("II", 35.0, II_NAME), _line("IPU", 150.0, "Imposto Predial(15%)"), _line(None, 10.0, "Sem tipo"),
    ])
    invoice = root.find(".//s:SalesInvoices/s:Invoice", NS)
    names = [etree.QName(c).localname for c in invoice]
    assert names[-4:] == ["DocumentTotals", "WithholdingTax", "WithholdingTax", "WithholdingTax"]
    got = [
        (w.findtext("s:WithholdingTaxType", namespaces=NS), w.findtext("s:WithholdingTaxDescription", namespaces=NS), w.findtext("s:WithholdingTaxAmount", namespaces=NS))
        for w in invoice.findall("s:WithholdingTax", NS)
    ]
    assert got == [("II", II_NAME, "100.00"), ("IPU", "Imposto Predial(15%)", "150.00"), ("OU", "Sem tipo", "10.00")]


def test_a_document_without_withholding_carries_none():
    root = _generate([_line(), _line()])
    assert root.find(".//s:SalesInvoices/s:Invoice/s:WithholdingTax", NS) is None