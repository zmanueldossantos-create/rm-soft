"""The A4 invoice follows the AGT model: Data de emissao 08/10/2026 - 15h45 (Luanda time), amounts with a decimal
comma, and the payments recorded on the document with the official name of their method."""
import io
from datetime import datetime, timezone

import pytest

from app.utils.pdf_generator import _emission_text, fmt, generate_factura_style_a4, generate_invoice_pdf_thermal


def test_amounts_and_emission_date_as_on_the_agt_model():
    assert fmt(4560) == "4 560,00" and fmt(1234567.5) == "1 234 567,50"
    created = datetime(2026, 10, 8, 14, 45, tzinfo=timezone.utc)  # 15h45 in Luanda
    assert _emission_text({"business_date": "2026-10-08", "created_at": created}) == "08/10/2026 - 15h45"
    assert _emission_text({"business_date": "2026-10-08"}) == "08/10/2026"


def test_the_invoice_shows_its_payments_and_its_emission_time():
    pypdf = pytest.importorskip("pypdf")
    line = {"quantity": 1.0, "unit_price": 4000.0, "discount_percent": 0, "line_subtotal": 4000.0, "vat_rate_snapshot": 14.0,
            "exemption_code": None, "exemption_reason": None, "service_line": False, "code": "PRT-FRANGO",
            "product_name_snapshot": "Frango grelhado", "unit_code": "UN", "iec_amount": 0, "iselo_amount": 0, "line_total": 4560.0}
    company = {"name": "Restaurante Teste", "nif": "5000999011", "address": "Rua X", "phone_number": "+244923100011",
               "logo_path": None, "bank_accounts": []}
    invoice = {"invoice_type": "FR", "series": "FR2026", "number": 11, "business_date": "2026-10-08",
               "created_at": datetime(2026, 10, 8, 14, 45, tzinfo=timezone.utc), "print_count": 1, "retention_total": 0,
               "vat_total": 560.0, "total": 4560.0, "amount_in_words": None, "observations": None,
               "qr_code_data": "test", "atcud": "SIMUL-1", "payments": [{"name": "Cartão débito", "amount": 4560.0}]}
    pdf = generate_factura_style_a4(invoice, [line], company, None)
    text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "08/10/2026 - 15h45" in text
    assert "Meios de pagamento" in text and "Cartão débito" in text and "4 560,00" in text
    ticket = generate_invoice_pdf_thermal({**invoice, "subtotal": 4000.0, "discount_global_percent": 0,
                                           "payment_method_name": None}, [line], company, None)
    text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(ticket)).pages)
    assert "Meios de pagamento" in text and "Cartão débito" in text and "1,00 UN" in text
