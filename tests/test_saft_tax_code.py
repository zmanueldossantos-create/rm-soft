"""The SAF-T tax code is the one recorded on the line (and on the company rate), never guessed from the percentage:
a 7 % INT line stays INT - the old guess put anything under 10 % in RED."""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def test_an_intermediate_rate_line_is_exported_as_int():
    line = {
        "product_code": "PRD-1", "product_name": "Produto", "quantity": 1.0, "unit_price": 100.0, "vat_rate": 7.0, "tax_code": "INT", "unit_code": "UN",
        "line_subtotal": 100.0, "line_vat": 7.0, "line_total": 107.0, "exemption_code": None,
    }
    doc = {
        "invoice_type": "FACTURA", "series": "S1", "number": 1,
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc", "subtotal": 100.0, "vat_total": 7.0, "total": 107.0,
        "customer_id": None, "lines": [line],
    }
    root = etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "PRD-1", "name": "Produto", "product_type": "BEM"}],
        vat_rates=[{"name": "Taxa intermedia", "rate": 7.0, "tax_code": "INT"}],
        invoices=[doc], fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))
    line_code = root.find(".//s:SalesInvoices/s:Invoice/s:Line/s:Tax/s:TaxCode", NS).text
    table_codes = [e.text for e in root.findall(".//s:TaxTable/s:TaxTableEntry/s:TaxCode", NS)]
    assert line_code == "INT"
    assert table_codes == ["INT"]


def test_the_unit_of_a_line_is_the_one_recorded_on_it():
    line = {
        "product_code": "PRD-1", "product_name": "Arroz", "quantity": 2.0, "unit_price": 21000.0, "vat_rate": 14.0,
        "tax_code": "NOR", "unit_code": "SC", "line_subtotal": 42000.0, "line_vat": 5880.0, "line_total": 47880.0,
        "exemption_code": None,
    }
    doc = {
        "invoice_type": "FACTURA", "series": "S1", "number": 2,
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 11, 0, 0),
        "atcud": "SIMUL-2", "invoice_hash": "SIMUL-def", "subtotal": 42000.0, "vat_total": 5880.0, "total": 47880.0,
        "customer_id": None, "lines": [line],
    }
    root = etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "PRD-1", "name": "Arroz", "product_type": "BEM"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}],
        invoices=[doc], fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))
    assert root.find(".//s:SalesInvoices/s:Invoice/s:Line/s:UnitOfMeasure", NS).text == "SC"
