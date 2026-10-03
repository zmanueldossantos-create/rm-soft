"""
Pro-formas are exported in SourceDocuments/WorkingDocuments (WorkType PP), like the AGT-validated Kiami exports:
same element order, WorkStatus N - or F once invoiced -, net TotalCredit, and no pro-forma among the invoices.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _doc(invoice_type, number, subtotal, vat, converted=False):
    total = subtotal + vat
    return {
        "invoice_type": invoice_type, "series": "S1", "number": number, 
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc",
        "subtotal": subtotal, "vat_total": vat, "total": total, "customer_id": None, "converted": converted,
        "lines": [{
            "product_code": "SRV-1", "product_name": "Servico", "quantity": 1.0, "unit_price": subtotal,
            "vat_rate": 14.0, "tax_code": "NOR", "line_subtotal": subtotal, "line_vat": vat, "line_total": total,
        }],
    }


def _generate(docs):
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "SRV-1", "name": "Servico", "product_type": "SERVICO"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}],
        invoices=docs, fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))


def _names(el, skip=()):
    return [etree.QName(c).localname for c in el if etree.QName(c).localname not in skip]


def test_pro_formas_are_exported_as_working_documents():
    root = _generate([_doc("FACTURA", 1, 1000.0, 140.0), _doc("PRO_FORMA", 1, 500.0, 70.0), _doc("PRO_FORMA", 2, 200.0, 28.0, converted=True)])
    working = root.find(".//s:SourceDocuments/s:WorkingDocuments", NS)
    assert working.findtext("s:NumberOfEntries", namespaces=NS) == "2"
    assert working.findtext("s:TotalCredit", namespaces=NS) == "700.00" and working.findtext("s:TotalDebit", namespaces=NS) == "0.00"

    docs = working.findall("s:WorkDocument", NS)
    assert [d.findtext("s:DocumentNumber", namespaces=NS) for d in docs] == ["PP S1/1", "PP S1/2"]
    assert [d.findtext("s:DocumentStatus/s:WorkStatus", namespaces=NS) for d in docs] == ["N", "F"]
    assert all(d.findtext("s:WorkType", namespaces=NS) == "PP" for d in docs)
    # element order of the AGT-validated Kiami exports
    assert _names(docs[0], skip=("Line",)) == [
        "DocumentNumber", "DocumentStatus", "Hash", "HashControl", "Period", "WorkDate", "WorkType",
        "SourceID", "SystemEntryDate", "CustomerID", "DocumentTotals",
    ]
    assert _names(docs[0].find("s:DocumentStatus", NS)) == ["WorkStatus", "WorkStatusDate", "SourceID", "SourceBilling"]
    # the invoice section holds the invoice only
    assert root.findtext(".//s:SalesInvoices/s:NumberOfEntries", namespaces=NS) == "1"


def test_a_walk_in_pro_forma_gets_the_generic_customer_and_no_section_without_pro_formas():
    root = _generate([_doc("PRO_FORMA", 1, 500.0, 70.0)])
    customers = [(c.findtext("s:CustomerID", namespaces=NS), c.findtext("s:CustomerTaxID", namespaces=NS)) for c in root.findall(".//s:MasterFiles/s:Customer", NS)]
    assert customers == [("0", "999999999")]
    assert root.findtext(".//s:WorkDocument/s:CustomerID", namespaces=NS) == "0"

    assert _generate([_doc("FACTURA", 1, 1000.0, 140.0)]).find(".//s:WorkingDocuments", NS) is None