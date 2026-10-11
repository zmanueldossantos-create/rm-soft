"""A Nota de Crédito prints the document it corrects (type, number, date) and its reason - on the A4 and on the
ticket; any other document prints none of it."""
import io

import pytest

from app.utils.pdf_generator import generate_factura_style_a4, generate_invoice_pdf_thermal

LINE = {"quantity": 1.0, "unit_price": 15000.0, "discount_percent": 0, "line_subtotal": 15000.0, "vat_rate_snapshot": 14.0,
        "exemption_code": None, "exemption_reason": None, "service_line": True, "code": "SPA-MAS60",
        "product_name_snapshot": "Massagem 60 min", "unit_code": "UN", "iec_amount": 0, "iselo_amount": 0, "line_total": 17100.0}
COMPANY = {"name": "Spa Teste", "nif": "5000999013", "address": "Rua Y", "phone_number": "+244923100018",
           "logo_path": None, "bank_accounts": []}


def _invoice(invoice_type, **extra):
    base = {"invoice_type": invoice_type, "series": invoice_type + "2026", "number": 1, "business_date": "2026-10-11",
            "print_count": 1, "retention_total": 0, "subtotal": 15000.0, "vat_total": 2100.0, "total": 17100.0,
            "discount_global_percent": 0, "amount_in_words": None, "observations": None, "qr_code_data": "test",
            "atcud": "SIMUL-1", "payments": [], "payment_method_name": None}
    base.update(extra)
    return base


def _texts(invoice):
    pypdf = pytest.importorskip("pypdf")
    return [" ".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
            for pdf in (generate_factura_style_a4(invoice, [LINE], COMPANY, None),
                        generate_invoice_pdf_thermal(invoice, [LINE], COMPANY, None))]


def test_the_credit_note_prints_its_origin_document_and_its_reason():
    note = _invoice("NC", credit_note_reason="ANL", credit_note_cause="Cliente desistiu",
                    reference_invoice={"invoice_type": "FR", "series": "FR2026", "number": 1, "business_date": "2026-10-11"})
    for text in _texts(note):
        assert "Documento de origem: FR FR2026/1 de 11/10/2026" in text
        assert "Motivo: Anulação - Cliente desistiu" in text
        assert "a creditar" in text


def test_an_invoice_prints_no_origin_document():
    for text in _texts(_invoice("FR")):
        assert "Documento de origem" not in text and "a creditar" not in text
