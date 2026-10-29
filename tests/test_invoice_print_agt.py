"""The printed documents carry what the AGT models (FACTURA.png, RECIBO.png) and the certified programs print: the
customer's NIF (999999999 for a final consumer) and contact, the taxes by rate with the reason of an exemption,
«XXXX-Processado por programa validado n.º …», no ATCUD; the receipt with its accents."""
import io
from datetime import datetime, timezone

import pytest

from app.utils.pdf_generator import (certification_text, customer_nif, generate_factura_style_a4,
                                      generate_invoice_pdf_thermal, generate_recibo_style_a4, hash_chars)

pypdf = pytest.importorskip("pypdf")

HASH = "SIMUL-" + "".join("0123456789abcdef"[i % 16] for i in range(40))
COMPANY = {"name": "Padaria Teste", "nif": "5000999001", "address": "Rua Rainha Ginga, 45", "city": "Luanda",
           "phone_number": "+244923999000", "logo_path": None,
           "bank_accounts": [{"acronym": "BAI", "account_number": "123", "iban": "AO06004000001234567890123"}]}
CUSTOMER = {"name": "Cliente Lda", "nif": "5000413178", "address": "Rua 9", "city": "Luanda",
            "phone_number": "+244924741714", "is_final_consumer": False}
LINES = [
    {"quantity": 1.0, "unit_price": 1000.0, "discount_percent": 0, "line_subtotal": 1000.0, "vat_rate_snapshot": 14.0,
     "exemption_code": None, "exemption_reason": None, "service_line": False, "code": "P1", "product_name_snapshot": "Pão",
     "unit_code": "UN", "iec_amount": 0, "iselo_amount": 0, "line_total": 1140.0},
    {"quantity": 1.0, "unit_price": 500.0, "discount_percent": 0, "line_subtotal": 500.0, "vat_rate_snapshot": 0.0,
     "exemption_code": "M11", "exemption_reason": "Isento nos termos da alínea b) do artigo 12.º do CIVA",
     "service_line": False, "code": "P2", "product_name_snapshot": "Leite", "unit_code": "UN", "iec_amount": 0,
     "iselo_amount": 0, "line_total": 500.0},
]
INVOICE = {"invoice_type": "FT", "series": "FT26SSEDEN", "number": 3, "business_date": "2026-10-29",
           "created_at": datetime(2026, 10, 29, 11, 5, tzinfo=timezone.utc), "print_count": 1, "retention_total": 0,
           "subtotal": 1500.0, "vat_total": 140.0, "total": 1640.0, "discount_global_percent": 0, "amount_in_words": None,
           "observations": None, "qr_code_data": "test", "atcud": "SIMUL-3", "payments": [], "invoice_hash": HASH,
           "software_validation_number": "131/AGT/2019", "payment_method_name": None}


def _text(pdf: bytes) -> str:
    return "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages)


def test_the_certification_phrase():
    assert hash_chars(HASH) == "0a4e"  # the 1st, 11th, 21st and 31st characters
    assert certification_text(HASH, "131/AGT/2019") == "0a4e-Processado por programa validado n.º 131/AGT/2019"
    assert certification_text(HASH, "0").endswith("Processado por programa não validado (simulação)")
    assert customer_nif(None) == customer_nif({"nif": ""}) == customer_nif({"nif": "5000", "is_final_consumer": True}) == "999999999"


def test_the_a4_invoice():
    text = _text(generate_factura_style_a4(INVOICE, LINES, COMPANY, CUSTOMER))
    assert "0a4e-Processado por programa validado n.º 131/AGT/2019" in text
    assert "ATCUD" not in text and "SIMUL" not in text
    assert "Nº de Contribuinte: 5000413178" in text and "Tel: +244924741714" in text
    assert "Resumo de impostos" in text and "M11 - Isento nos termos da alínea b)" in text
    assert "1 000,00" in text and "140,00" in text  # the 14 % base and its tax
    assert "IBAN: AO06004000001234567890123" in text and "Rua Rainha Ginga, 45 - Luanda" in text
    anonymous = _text(generate_factura_style_a4(INVOICE, LINES, COMPANY, None))
    assert "Consumidor Final" in anonymous and "Nº de Contribuinte: 999999999" in anonymous


def test_the_ticket():
    text = _text(generate_invoice_pdf_thermal(INVOICE, LINES, COMPANY, None))
    assert "NIF: 999999999" in text and "Resumo de impostos" in text and "M11" in text
    assert "0a4e-Processado por programa validado" in text and "SIMUL" not in text
    text = _text(generate_invoice_pdf_thermal(INVOICE, LINES, COMPANY, CUSTOMER))
    assert "Contacto: +244924741714" in text and "NIF: 5000413178" in text


def test_the_receipt():
    receipt = {**INVOICE, "invoice_type": "RC", "number": 1, "series": "RC26SSEDEN", "reference_invoice": {
        "invoice_type": "FT", "series": "FT26SSEDEN", "number": 3, "business_date": "2026-10-20",
        "subtotal": 1500.0, "vat_total": 140.0, "total": 1640.0}}
    text = _text(generate_recibo_style_a4(receipt, COMPANY, CUSTOMER)).replace(": \n", ": ")  # label, value
    for words in ("Data de emissão: 29/10/2026 - 12h05", "Localização: Rua 9 - Luanda", "Contacto: +244924741714",
                  "NIF: 5000413178",
                  "Documento de Cobrança", "Data emissão: 20/10/2026", "Taxa de Câmbios", "Nº de Contribuinte: 5000999001",
                  "Luanda - Angola", "0a4e-Processado por programa validado n.º 131/AGT/2019"):
        assert words in text, words
    assert "SIMUL" not in text
