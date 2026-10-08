"""
PDF (A4 and 80mm ticket): the withholding is printed with the net amount to pay, and the exemption motive is the
official reason of the code copied on the line (legend below the A4 tax summary, wrapped on the ticket).
"""
import textwrap
from unittest.mock import patch

from reportlab.pdfgen import canvas as rl_canvas

# Official reason of M11 (AGT exemption table), as the catalog gives it and the line records it when issued.
M11_REASON = "Isento nos termos da al\u00ednea b) do n\u00ba1 do artigo 12.\u00ba do CIVA"
from app.utils.pdf_generator import generate_invoice_pdf_a4, generate_invoice_pdf_thermal

COMPANY = {
    "name": "Empresa Teste", "nif": "5000000001", "address": None, "phone_number": None, "phone_number_2": None,
    "email": None, "website": None, "logo_path": None, "bank_accounts": [],
}
LINES = [
    {"code": "SRV-1", "unit": "UN", "product_name_snapshot": "Servico taxado", "quantity": 1.0, "unit_price": 100.0,
     "discount_percent": 0.0, "vat_rate_snapshot": 14.0, "line_subtotal": 100.0, "line_total": 114.0, "exemption_code": None},
    {"code": "SRV-2", "unit": "UN", "product_name_snapshot": "Servico isento", "quantity": 1.0, "unit_price": 100.0,
     "discount_percent": 0.0, "vat_rate_snapshot": 0.0, "line_subtotal": 100.0, "line_total": 100.0, "exemption_code": "M11", "exemption_reason": M11_REASON},
]


def _invoice(retention):
    return {
        "invoice_type": "FT", "series": "S1", "number": 2, "business_date": "2026-09-20", "due_date": None,
        "payment_method_name": None, "payment_term_name": None, "subtotal": 200.0, "vat_total": 14.0, "total": 214.0,
        "retention_total": retention, "discount_global_percent": 0.0, "observations": None, "print_count": 1,
        "is_fiscal_doc": True, "amount_in_words": None, "qr_code_data": "SIMUL",
    }


def _texts(generate, invoice):
    seen = []

    def recording(name):
        original = getattr(rl_canvas.Canvas, name)

        def inner(self, x, y, text, *args, **kwargs):
            seen.append(str(text))
            return original(self, x, y, text, *args, **kwargs)
        return inner

    with patch.object(rl_canvas.Canvas, "drawString", recording("drawString")), \
         patch.object(rl_canvas.Canvas, "drawRightString", recording("drawRightString")), \
         patch.object(rl_canvas.Canvas, "drawCentredString", recording("drawCentredString")):
        pdf = generate(invoice, LINES, COMPANY, None)
    assert pdf.startswith(b"%PDF")
    return seen


def test_a4_prints_the_withholding_and_the_official_exemption_reason():
    seen = _texts(generate_invoice_pdf_a4, _invoice(10.0))
    assert "Retenção na fonte" in seen and "Líquido a pagar" in seen
    assert "204,00" in seen  # 214 - 10
    assert "M11" in seen
    assert "M11 - " + M11_REASON in seen


def test_a4_without_withholding_prints_no_withholding_rows():
    seen = _texts(generate_invoice_pdf_a4, _invoice(0.0))
    assert "Retenção na fonte" not in seen and "Líquido a pagar" not in seen


def test_ticket_prints_the_withholding_and_wraps_the_official_reason():
    seen = _texts(generate_invoice_pdf_thermal, _invoice(10.0))
    assert "Retencao:" in seen and "Liquido a pagar:" in seen
    assert textwrap.wrap(M11_REASON, 28)[0] in seen