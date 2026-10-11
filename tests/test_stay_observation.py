"""Hotel point 2, subject 3: the guest of a stay on its invoice - an Observações line (guest, room, dates in
Luanda time), never in place of the fiscal customer; printed on the A4 and on the ticket."""
import io
from datetime import datetime, timezone

import pytest

from app.services.stay_text import stay_observation
from app.utils.pdf_generator import generate_factura_style_a4, generate_invoice_pdf_thermal


def test_the_observation_names_the_guest_the_room_and_the_dates_in_luanda_time():
    starts = datetime(2026, 10, 11, 13, 0, tzinfo=timezone.utc)  # 14:00 in Luanda
    ends = datetime(2026, 10, 13, 11, 0, tzinfo=timezone.utc)    # 12:00 in Luanda
    assert stay_observation("Quarto 101", starts, ends, "Família Teste", 2) == \
        "Hóspede: Família Teste (2 pax) - Quarto 101 - 11/10/2026 14:00 a 13/10/2026 12:00"
    assert stay_observation("Quarto 101", starts, ends) == "Quarto 101 - 11/10/2026 14:00 a 13/10/2026 12:00"


def test_the_a4_and_the_ticket_print_the_observation():
    pypdf = pytest.importorskip("pypdf")
    line = {"quantity": 2.0, "unit_price": 25000.0, "discount_percent": 0, "line_subtotal": 50000.0, "vat_rate_snapshot": 14.0,
            "exemption_code": None, "exemption_reason": None, "service_line": True, "code": "DIA-STD",
            "product_name_snapshot": "Diária", "unit_code": "UN", "iec_amount": 0, "iselo_amount": 0, "line_total": 57000.0}
    company = {"name": "Hotel Teste", "nif": "5000999012", "address": "Rua Y", "phone_number": "+244923100016",
               "logo_path": None, "bank_accounts": []}
    observation = "Hóspede: Família Teste (2 pax) - Quarto 101 - 11/10/2026 14:00 a 13/10/2026 12:00"
    invoice = {"invoice_type": "FR", "series": "FR2026", "number": 3, "business_date": "2026-10-13", "print_count": 1,
               "retention_total": 0, "subtotal": 50000.0, "vat_total": 7000.0, "total": 57000.0, "discount_global_percent": 0,
               "amount_in_words": None, "observations": observation, "qr_code_data": "test", "atcud": "SIMUL-3",
               "payments": [{"name": "Numerário", "amount": 57000.0}], "payment_method_name": None}
    for pdf in (generate_factura_style_a4(invoice, [line], company, None),
                generate_invoice_pdf_thermal(invoice, [line], company, None)):
        text = " ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
        assert "Família Teste" in text and "Quarto 101" in text
        assert "Consumidor Final" in text  # the fiscal customer is unchanged
