"""
XSD Payments: a receipt is exported as a Payment (PaymentType RC) with the payment methods and the cash received, one
line for the settled invoice, the settled totals and the withholding by type. A receipt whose invoice is unknown is
left out, and a document set without receipts has no Payments section.
"""
from datetime import date, datetime

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}


def _receipt(number, methods=None, withholding=None, reference="FT S1/1"):
    return {
        "invoice_type": "RECIBO", "series": "RC1", "number": number, "number_digits": 3,
        "business_date": date(2026, 9, 20), "created_at": datetime(2026, 9, 20, 10, 0, 0),
        "atcud": "SIMUL-1", "invoice_hash": "SIMUL-abc",
        "subtotal": 2000.0, "vat_total": 280.0, "total": 2280.0, "customer_id": None, "lines": [],
        "reference_invoice_no": reference, "reference_invoice_date": date(2026, 9, 1),
        "payment_methods": [{"code": "NU", "amount": 2150.0}] if methods is None else methods,
        "withholding": [{"type": "II", "name": "Retencao na fonte(6,5)", "amount": 130.0}] if withholding is None else withholding,
    }


def _generate(docs):
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Empresa", "nif": "5000000001", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[], vat_rates=[{"name": "Taxa normal", "rate": 14.0}],
        invoices=docs, fiscal_year=2026, start_date=date(2026, 9, 1), end_date=date(2026, 9, 30),
    ))


def _names(el):
    return [etree.QName(c).localname for c in el]


def test_receipts_are_exported_as_payments():
    root = _generate([_receipt(1), _receipt(2, methods=[{"code": "XX", "amount": 100.0}], withholding=[])])
    payments = root.find(".//s:SourceDocuments/s:Payments", NS)
    assert payments.findtext("s:NumberOfEntries", namespaces=NS) == "2"
    assert payments.findtext("s:TotalCredit", namespaces=NS) == "4000.00" and payments.findtext("s:TotalDebit", namespaces=NS) == "0.00"

    first, second = payments.findall("s:Payment", NS)
    assert first.findtext("s:PaymentRefNo", namespaces=NS) == "RC RC1/1" and first.findtext("s:PaymentType", namespaces=NS) == "RC"
    assert _names(first) == [
        "PaymentRefNo", "Period", "TransactionDate", "PaymentType", "DocumentStatus", "PaymentMethod", "SourceID",
        "SystemEntryDate", "CustomerID", "Line", "DocumentTotals", "WithholdingTax",
    ]
    assert _names(first.find("s:DocumentStatus", NS)) == ["PaymentStatus", "PaymentStatusDate", "SourceID", "SourcePayment"]
    method = first.find("s:PaymentMethod", NS)
    assert (method.findtext("s:PaymentMechanism", namespaces=NS), method.findtext("s:PaymentAmount", namespaces=NS)) == ("NU", "2150.00")
    line = first.find("s:Line", NS)
    assert line.findtext("s:SourceDocumentID/s:OriginatingON", namespaces=NS) == "FT S1/1"
    assert line.findtext("s:SourceDocumentID/s:InvoiceDate", namespaces=NS) == "2026-09-01"
    assert line.findtext("s:CreditAmount", namespaces=NS) == "2000.00"
    totals = first.find("s:DocumentTotals", NS)
    assert [totals.findtext("s:" + k, namespaces=NS) for k in ("TaxPayable", "NetTotal", "GrossTotal")] == ["280.00", "2000.00", "2280.00"]
    tax = first.find("s:WithholdingTax", NS)
    assert (tax.findtext("s:WithholdingTaxType", namespaces=NS), tax.findtext("s:WithholdingTaxAmount", namespaces=NS)) == ("II", "130.00")

    assert second.find("s:PaymentMethod/s:PaymentMechanism", NS).text == "OU"  # unknown mechanism
    assert second.find("s:WithholdingTax", NS) is None
    assert root.findtext(".//s:SalesInvoices/s:NumberOfEntries", namespaces=NS) == "0"  # a receipt is not an invoice


def test_no_payments_section_without_a_usable_receipt_and_generic_customer_for_a_walk_in_receipt():
    assert _generate([]).find(".//s:Payments", NS) is None
    assert _generate([_receipt(1, reference=None)]).find(".//s:Payments", NS) is None  # invoice unknown: left out

    root = _generate([_receipt(1)])
    assert root.findtext(".//s:Payments/s:Payment/s:CustomerID", namespaces=NS) == "0"
    assert [(c.findtext("s:CustomerID", namespaces=NS), c.findtext("s:CustomerTaxID", namespaces=NS)) for c in root.findall(".//s:MasterFiles/s:Customer", NS)] == [("0", "999999999")]