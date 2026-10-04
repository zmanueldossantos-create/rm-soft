"""
Tests for the customers section of the SAF-T generator: a walk-in sale (no customer) points at the company's
own "Consumidor final" customer when it has one (no second generic entry with the same tax ID), otherwise the
generic entry (CustomerID 0) is added; CustomerIDs follow the order of the list given.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _customer(cid, nif, name):
    return {"id": cid, "nif": nif, "name": name, "address": None, "phone_number": None, "email": None}


def _invoice(customer_id):
    return {
        "invoice_type": "FACTURA", "series": "FT1S1N", "number": 1, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc",
        "subtotal": 1000.0, "vat_total": 140.0, "total": 1140.0,
        "customer_id": customer_id,
        "lines": [{
            "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": 1000.0,
            "vat_rate": 14.0, "tax_code": "NOR", "unit_code": "UN", "line_subtotal": 1000.0, "line_vat": 140.0, "line_total": 1140.0,
        }],
    }


def _generate(customers, invoices):
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=customers,
        products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}],
        invoices=invoices, fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))


def _master(root):
    return [(c.findtext("s:CustomerID", namespaces=NS), c.findtext("s:CustomerTaxID", namespaces=NS), c.findtext("s:CompanyName", namespaces=NS))
            for c in root.findall(".//s:MasterFiles/s:Customer", NS)]


def _invoice_customer(root):
    return root.findtext(".//s:SalesInvoices/s:Invoice/s:CustomerID", namespaces=NS)


def test_walk_in_sale_uses_the_companys_own_final_consumer_without_a_second_generic_entry():
    customers = [_customer("c-1", "5000999002", "Empresa Cliente"), _customer("c-2", "999999999", "Cliente Particular")]
    root = _generate(customers, [_invoice(None)])
    master = _master(root)
    assert [m[0] for m in master] == ["1", "2"]  # no extra generic entry
    assert [m[1] for m in master].count("999999999") == 1
    assert master[1][2] == "Consumidor final"  # designation required by the XSD
    assert _invoice_customer(root) == "2"


def test_walk_in_sale_without_an_own_final_consumer_gets_the_generic_entry():
    root = _generate([_customer("c-1", "5000999002", "Empresa Cliente")], [_invoice(None)])
    master = _master(root)
    assert master[-1] == ("0", "999999999", "Consumidor final")
    assert _invoice_customer(root) == "0"


def test_named_customer_invoice_references_its_own_id_and_adds_no_generic_entry():
    root = _generate([_customer("c-1", "5000999002", "Empresa Cliente")], [_invoice("c-1")])
    assert [m[0] for m in _master(root)] == ["1"]
    assert _invoice_customer(root) == "1"