"""
SAF-T (AO) XML generator - Modo Fatura, monthly export submitted manually
to the AGT portal (see specification v6/v7, section 4.2 and the two-mode
decision: Modo Fatura vs Faturacao Eletronica).

Structure verified against the official XSD (SAFTAO1_01_01) and a real
AGT-validated sample file (Kiami software) - see project decisions on
SAF-T generator. Namespace, field order and cardinality all confirmed
directly in the schema, not guessed.

Compliance notes:
- HashControl = "0" because RM SOFT is not yet AGT-homologated (per XSD:
  "preencher com 0 caso o documento seja gerado por um programa nao
  validado"). Hash itself carries our existing simulated invoice_hash.
- ShipTo/ShipFrom/GeneralLedgerAccounts are optional (minOccurs=0) and
  omitted - not applicable to counter retail without delivery tracking.
- Walk-in sales with no Customer use the generic "Consumidor final"
  entry (CustomerID=0, CustomerTaxID=999999999) per XSD documentation.
- TaxExemptionReason/Code are only emitted for ISE (0%) lines.
"""
from datetime import date, datetime
from decimal import Decimal

from lxml import etree

NSMAP = {None: "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"}
NS = "urn:OECD:StandardAuditFile-Tax:AO_1.01_01"

FINAL_CONSUMER_ID = "0"
FINAL_CONSUMER_TAX_ID = "999999999"

INVOICE_TYPE_MAP = {
    "FACTURA": "FT",
    "FACTURA_RECIBO": "FR",
    "NOTA_CREDITO": "NC",
    "NOTA_DEBITO": "ND",
}


def _q(tag: str) -> str:
    """Qualifies a tag name with the SAF-T namespace."""
    return f"{{{NS}}}{tag}"


def _el(parent, tag: str, text=None):
    """Creates a namespaced sub-element with optional text content."""
    e = etree.SubElement(parent, _q(tag))
    if text is not None:
        e.text = str(text)
    return e


def _money(value) -> str:
    """Formats a monetary value with exactly 2 decimals, dot separator (SAF-T requires this, not locale formatting)."""
    return f"{Decimal(str(value)):.2f}"


def _map_tax_code(rate: float) -> str:
    """Maps a VAT percentage to its SAF-T TaxCode - NOR (14%), RED (5%), ISE (0%)."""
    rate = float(rate)
    if rate <= 0:
        return "ISE"
    if rate < 10:
        return "RED"
    return "NOR"


def generate_saf_t_xml(
    company: dict,
    platform_settings: dict,
    customers: list[dict],
    products: list[dict],
    vat_rates: list[dict],
    invoices: list[dict],
    fiscal_year: int,
    start_date: date,
    end_date: date,
) -> bytes:
    """
    Builds the complete AuditFile XML for one fiscal period (typically one
    calendar month, per section 4.2 "Modo Fatura" - exported at month end).

    invoices: list of {
        "invoice_type": str, "series": str, "number": int, "business_date": date,
        "created_at": datetime, "atcud": str, "invoice_hash": str,
        "subtotal": float, "vat_total": float, "total": float,
        "customer_id": str | None, "customer_nif": str | None,
        "lines": [{"product_code": str, "product_name": str, "quantity": float,
                    "unit_price": float, "vat_rate": float, "line_subtotal": float,
                    "line_vat": float, "line_total": float}],
    }
    """
    root = etree.Element(_q("AuditFile"), nsmap=NSMAP)

    # ---------- Header ----------
    header = _el(root, "Header")
    _el(header, "AuditFileVersion", "1.01_01")
    _el(header, "CompanyID", company.get("commercial_registration_number") or company["nif"])
    _el(header, "TaxRegistrationNumber", company["nif"])
    _el(header, "TaxAccountingBasis", "F")  # Facturacao only - RM SOFT does not do integrated accounting
    _el(header, "CompanyName", company["name"])
    _el(header, "BusinessName", company["name"])

    address = _el(header, "CompanyAddress")
    _el(address, "BuildingNumber", "S/N")
    _el(address, "AddressDetail", company.get("address") or "Desconhecido")
    _el(address, "City", "Desconhecido")
    _el(address, "PostalCode", "0000")
    _el(address, "Province", "Desconhecido")
    _el(address, "Country", "AO")

    _el(header, "FiscalYear", fiscal_year)
    _el(header, "StartDate", start_date.isoformat())
    _el(header, "EndDate", end_date.isoformat())
    _el(header, "CurrencyCode", "AOA")
    _el(header, "DateCreated", date.today().isoformat())
    _el(header, "TaxEntity", "Global")
    _el(header, "ProductCompanyTaxID", platform_settings.get("vendor_tax_id") or "000000000")
    _el(header, "SoftwareValidationNumber", platform_settings.get("software_validation_number") or "0")
    _el(header, "ProductID", platform_settings.get("product_id") or "RMSOFT/RMSOFT")
    _el(header, "ProductVersion", platform_settings.get("product_version") or "1.0")
    _el(header, "Telephone", company.get("phone_number") or "Desconhecido")
    _el(header, "Email", company.get("email") or "Desconhecido")

    # ---------- MasterFiles ----------
    master_files = _el(root, "MasterFiles")

    has_walk_in_sale = any(inv.get("customer_id") is None for inv in invoices)
    # The company may already hold its own "Consumidor final" customer (NIF 999999999): a walk-in sale then
    # points at it and no second generic entry is added (two records with the same tax ID otherwise).
    own_final_consumer = next((c for c in customers if c["nif"] == FINAL_CONSUMER_TAX_ID), None)

    # SAF-T CustomerID must be short (max 30 chars) - our internal UUIDs are
    # too long, so we assign sequential short IDs here and remember the
    # mapping to reference the same customer correctly from each Invoice.
    customer_short_id = {c["id"]: str(idx + 1) for idx, c in enumerate(customers)}

    for c in customers:
        customer_el = _el(master_files, "Customer")
        _el(customer_el, "CustomerID", customer_short_id[c["id"]])
        _el(customer_el, "AccountID", "Desconhecido")
        _el(customer_el, "CustomerTaxID", c["nif"])
        # XSD: the generic final-consumer customer is designated "Consumidor final".
        _el(customer_el, "CompanyName", "Consumidor final" if c["nif"] == FINAL_CONSUMER_TAX_ID else c["name"])
        _el(customer_el, "Contact", "Desconhecido")
        billing = _el(customer_el, "BillingAddress")
        _el(billing, "BuildingNumber", "S/N")
        _el(billing, "StreetName", "Desconhecido")
        _el(billing, "AddressDetail", c.get("address") or "Desconhecido")
        _el(billing, "City", "Desconhecido")
        _el(billing, "PostalCode", "0000")
        _el(billing, "Province", "Desconhecido")
        _el(billing, "Country", "AO")
        _el(customer_el, "Telephone", c.get("phone_number") or "Desconhecido")
        _el(customer_el, "Email", c.get("email") or "Desconhecido")
        _el(customer_el, "SelfBillingIndicator", "0")

    if has_walk_in_sale and own_final_consumer is None:
        generic = _el(master_files, "Customer")
        _el(generic, "CustomerID", FINAL_CONSUMER_ID)
        _el(generic, "AccountID", "Desconhecido")
        _el(generic, "CustomerTaxID", FINAL_CONSUMER_TAX_ID)
        _el(generic, "CompanyName", "Consumidor final")
        _el(generic, "Contact", "Desconhecido")
        billing = _el(generic, "BillingAddress")
        _el(billing, "BuildingNumber", "S/N")
        _el(billing, "StreetName", "Desconhecido")
        _el(billing, "AddressDetail", "Desconhecido")
        _el(billing, "City", "Desconhecido")
        _el(billing, "PostalCode", "0000")
        _el(billing, "Province", "Desconhecido")
        _el(billing, "Country", "AO")
        _el(generic, "Telephone", "Desconhecido")
        _el(generic, "Email", "Desconhecido")
        _el(generic, "SelfBillingIndicator", "0")

    for p in products:
        product_el = _el(master_files, "Product")
        saft_product_type = "S" if p.get("product_type") == "SERVICO" else "P"
        _el(product_el, "ProductType", saft_product_type)
        _el(product_el, "ProductCode", p["code"])
        _el(product_el, "ProductGroup", "Geral")
        _el(product_el, "ProductDescription", p["name"])
        _el(product_el, "ProductNumberCode", p["code"])

    tax_table = _el(master_files, "TaxTable")
    for v in vat_rates:
        entry = _el(tax_table, "TaxTableEntry")
        _el(entry, "TaxType", "IVA")
        _el(entry, "TaxCountryRegion", "AO")
        _el(entry, "TaxCode", _map_tax_code(v["rate"]))
        _el(entry, "Description", v["name"])
        _el(entry, "TaxPercentage", _money(v["rate"]))

    # ---------- SourceDocuments.SalesInvoices ----------
    source_documents = _el(root, "SourceDocuments")
    sales_invoices = _el(source_documents, "SalesInvoices")
    _el(sales_invoices, "NumberOfEntries", len(invoices))
    _el(sales_invoices, "TotalDebit", "0.00")
    total_credit = sum(float(inv["total"]) for inv in invoices)
    _el(sales_invoices, "TotalCredit", _money(total_credit))

    for inv in invoices:
        saft_type = INVOICE_TYPE_MAP.get(inv["invoice_type"], "FT")
        invoice_el = _el(sales_invoices, "Invoice")
        _el(invoice_el, "InvoiceNo", f"{saft_type} {inv['series']}/{inv['number']}")

        status = _el(invoice_el, "DocumentStatus")
        _el(status, "InvoiceStatus", "N")
        _el(status, "InvoiceStatusDate", inv["created_at"].strftime("%Y-%m-%dT%H:%M:%S"))
        _el(status, "SourceID", "RMSOFT")
        _el(status, "SourceBilling", "P")

        _el(invoice_el, "Hash", inv["invoice_hash"])
        _el(invoice_el, "HashControl", "0")
        _el(invoice_el, "Period", inv["business_date"].month)
        _el(invoice_el, "InvoiceDate", inv["business_date"].isoformat())
        _el(invoice_el, "InvoiceType", saft_type)

        special = _el(invoice_el, "SpecialRegimes")
        _el(special, "SelfBillingIndicator", "0")
        _el(special, "CashVATSchemeIndicator", "0")
        _el(special, "ThirdPartiesBillingIndicator", "0")

        _el(invoice_el, "SourceID", "RMSOFT")
        _el(invoice_el, "SystemEntryDate", inv["created_at"].strftime("%Y-%m-%dT%H:%M:%S"))
        real_customer_id = inv.get("customer_id")
        walk_in_id = customer_short_id[own_final_consumer["id"]] if own_final_consumer else FINAL_CONSUMER_ID
        short_customer_id = customer_short_id.get(real_customer_id, walk_in_id) if real_customer_id else walk_in_id
        _el(invoice_el, "CustomerID", short_customer_id)

        for idx, line in enumerate(inv["lines"], start=1):
            line_el = _el(invoice_el, "Line")
            _el(line_el, "LineNumber", idx)
            _el(line_el, "ProductCode", line["product_code"])
            _el(line_el, "ProductDescription", line["product_name"])
            _el(line_el, "Quantity", f"{Decimal(str(line['quantity'])):.3f}")
            _el(line_el, "UnitOfMeasure", "UN")
            _el(line_el, "UnitPrice", _money(line["unit_price"]))
            _el(line_el, "TaxPointDate", inv["business_date"].isoformat())
            _el(line_el, "Description", line["product_name"])
            _el(line_el, "CreditAmount", _money(line["line_subtotal"]))

            tax = _el(line_el, "Tax")
            _el(tax, "TaxType", "IVA")
            _el(tax, "TaxCountryRegion", "AO")
            tax_code = _map_tax_code(line["vat_rate"])
            _el(tax, "TaxCode", tax_code)
            _el(tax, "TaxPercentage", _money(line["vat_rate"]))

            if tax_code == "ISE":
                _el(line_el, "TaxExemptionReason", "IVA - Regime de exclusao")
                _el(line_el, "TaxExemptionCode", "M04")

            _el(line_el, "SettlementAmount", "0.00")

        totals = _el(invoice_el, "DocumentTotals")
        _el(totals, "TaxPayable", _money(inv["vat_total"]))
        _el(totals, "NetTotal", _money(inv["subtotal"]))
        _el(totals, "GrossTotal", _money(inv["total"]))

    return etree.tostring(root, xml_declaration=True, encoding="utf-8", pretty_print=True)
