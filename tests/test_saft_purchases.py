"""Point 12, step 5: the purchase invoices in the SAF-T - only when the company asks for them (the file is then of
the type Q instead of F), with their suppliers in MasterFiles, each document as printed (number, hash, type; a credit
note refers to its invoice) and its deductible VAT by destination. The file is valid against the SAF-T AO schema."""
from datetime import date, datetime
from pathlib import Path

from lxml import etree

from app.utils.saf_t_generator import generate_saf_t_xml

NS = {"s": "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}
SCHEMA = etree.XMLSchema(etree.parse(str(Path(__file__).parent / "data" / "SAFTAO1.01_01.xsd")))


def _generate(suppliers=None, purchases=None):
    sale = {
        "invoice_type": "FACTURA_RECIBO", "series": "FR2026", "number": 1, "business_date": date(2026, 10, 4),
        "created_at": datetime(2026, 10, 4, 10, 0, 0), "atcud": "0", "invoice_hash": "abcd", "subtotal": 100.0,
        "vat_total": 14.0, "total": 114.0, "customer_id": None,
        "lines": [{"product_code": "PAO", "product_name": "Pão", "quantity": 1.0, "unit_price": 100.0, "vat_rate": 14.0,
                   "tax_code": "NOR", "unit_code": "UN", "line_subtotal": 100.0, "line_vat": 14.0, "line_total": 114.0}],
    }
    return etree.fromstring(generate_saf_t_xml(
        company={"name": "Padaria", "nif": "5000999010", "address": None, "phone_number": None, "email": None,
                 "commercial_registration_number": None},
        platform_settings={"software_validation_number": None, "vendor_tax_id": None, "product_id": None, "product_version": None},
        customers=[], products=[{"code": "PAO", "name": "Pão", "product_type": "BEM"}],
        vat_rates=[{"name": "Taxa normal", "rate": 14.0, "tax_code": "NOR"}], invoices=[sale],
        fiscal_year=2026, start_date=date(2026, 10, 1), end_date=date(2026, 10, 31),
        suppliers=suppliers, purchases=purchases,
    ))


def test_without_purchases_the_file_stays_an_invoicing_one():
    root = _generate()
    assert root.findtext("s:Header/s:TaxAccountingBasis", namespaces=NS) == "F"
    assert root.find("s:SourceDocuments/s:PurchaseInvoices", NS) is None
    SCHEMA.assertValid(root)


def test_purchases_are_declared_with_their_supplier_and_deductible_vat():
    supplier = {"id": "sup-1", "name": "Moagem do Kikolo", "nif": "5000111222", "address": None, "phone_number": None,
                "email": None, "country": "AO"}
    invoice = {"invoice_no": "FT A/123", "hash": "X1y2", "purchase_type": "FT", "invoice_date": date(2026, 10, 14),
               "period": 10, "supplier_id": "sup-1", "source_id": "+244923100011", "vat_total": 1680.0,
               "subtotal": 12000.0, "total": 13680.0, "deductible_pct": 100.0,
               "deductible": [{"type": "INV", "base": 12000.0, "amount": 1680.0}], "reference": None}
    credit = {**invoice, "invoice_no": "NC A/5", "hash": "0", "purchase_type": "NC", "vat_total": 140.0, "subtotal": 1000.0,
              "total": 1140.0, "deductible": [{"type": "INV", "base": 1000.0, "amount": 140.0}],
              "reference": {"no": "FT A/123", "date": date(2026, 10, 14)}}
    root = _generate([supplier], [invoice, credit])
    SCHEMA.assertValid(root)
    assert root.findtext("s:Header/s:TaxAccountingBasis", namespaces=NS) == "Q"
    assert root.findtext("s:MasterFiles/s:Supplier/s:SupplierTaxID", namespaces=NS) == "5000111222"
    docs = root.findall("s:SourceDocuments/s:PurchaseInvoices/s:Invoice", NS)
    assert [(d.findtext("s:InvoiceNo", namespaces=NS), d.findtext("s:PurchaseType", namespaces=NS),
             d.findtext("s:Hash", namespaces=NS), d.findtext("s:SupplierID", namespaces=NS)) for d in docs] == [
        ("FT A/123", "FT", "X1y2", "F1"), ("NC A/5", "NC", "0", "F1")]
    assert docs[1].findtext("s:References/s:Reference", namespaces=NS) == "FT A/123"
    deductible = docs[0].find("s:DocumentTotals/s:Deductible", NS)
    assert [deductible.findtext(f"s:{tag}", namespaces=NS) for tag in
            ("TaxBase", "DeductibleAmount", "DeductiblePercentage", "DeductibleTaxType")] == ["12000.00", "1680.00", "100.00", "INV"]
