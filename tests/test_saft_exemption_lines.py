"""
An exempt line carries the exemption code and official reason copied on it when issued. A line without them is an
error: nothing is guessed (the old fallback to M04 is gone).
"""
from datetime import date, datetime

import pytest
from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}
M04 = "IVA \u2013 Regime de Exclus\u00e3o"
M11 = "Isento nos termos da al\u00ednea b) do n\u00ba1 do artigo 12.\u00ba do CIVA"


def _line(code, reason):
    return {
        "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": 100.0, "vat_rate": 0.0, "tax_code": "ISE",
        "line_subtotal": 100.0, "line_vat": 0.0, "line_total": 100.0, "exemption_code": code, "exemption_reason": reason,
    }


def test_exempt_lines_carry_their_code_and_official_reason():
    doc = {
        "invoice_type": "FACTURA", "series": "S1", "number": 1, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc", "subtotal": 300.0, "vat_total": 0.0, "total": 300.0,
        "customer_id": None, "lines": [_line("M11", M11), _line("M04", M04)],
    }
    root = etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Isento", "rate": 0.0, "tax_code": "ISE"}],
        invoices=[doc], fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))
    lines = root.findall(".//s:SalesInvoices/s:Invoice/s:Line", NS)
    got = [(l.findtext("s:TaxExemptionCode", namespaces=NS), l.findtext("s:TaxExemptionReason", namespaces=NS)) for l in lines]
    assert got == [("M11", M11), ("M04", M04)]


def test_an_exempt_line_without_its_motive_cannot_be_exported():
    doc = {
        "invoice_type": "FACTURA", "series": "S1", "number": 2,
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 11, 0, 0),
        "atcud": "SIMUL-2", "invoice_hash": "SIMUL-def", "subtotal": 100.0, "vat_total": 0.0, "total": 100.0,
        "customer_id": None, "lines": [_line(None, None)],
    }
    with pytest.raises(ValueError, match="sem motivo de isencao"):
        generate_saf_t_xml(
            company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                     "commercial_registration_number": None},
            platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
            customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
            vat_rates=[{"name": "Isento", "rate": 0.0, "tax_code": "ISE"}],
            invoices=[doc], fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
        )
