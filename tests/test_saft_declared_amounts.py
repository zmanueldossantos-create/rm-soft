"""The SAF-T declares each line after all its discounts (SettlementAmount = its own + its share of the global one)
and the document's NetTotal and TaxPayable after the global discount - FR2026/7: 600 at 10 % -> 540 + 75,60."""
from app.services.saf_t_export_service import _apply_declared_amounts


def _line(qty, price, subtotal, rate=14.0):
    return {"quantity": qty, "unit_price": price, "line_subtotal": subtotal, "vat_rate": rate}


def test_a_global_discount_is_spread_over_the_lines():
    doc = {"invoice_type": "FACTURA_RECIBO", "subtotal": 600.0, "vat_total": 84.0, "total": 615.6,
           "lines": [_line(1, 600.0, 600.0)]}
    _apply_declared_amounts(doc, 10)
    assert (doc["subtotal"], doc["vat_total"]) == (540.0, 75.6)
    assert (doc["lines"][0]["line_subtotal"], doc["lines"][0]["settlement"]) == (540.0, 60.0)


def test_a_line_discount_is_declared_even_without_a_global_one():
    doc = {"invoice_type": "FACTURA", "subtotal": 900.0, "vat_total": 126.0, "total": 1026.0,
           "lines": [_line(2, 500.0, 900.0)]}  # 1000 less 10 % on the line
    _apply_declared_amounts(doc, 0)
    assert doc["lines"][0]["settlement"] == 100.0 and doc["subtotal"] == 900.0  # stored values unchanged


def test_a_receipt_is_left_as_it_is():
    doc = {"invoice_type": "RECIBO", "subtotal": 600.0, "vat_total": 84.0, "total": 684.0, "lines": []}
    _apply_declared_amounts(doc, 10)
    assert (doc["subtotal"], doc["vat_total"]) == (600.0, 84.0)
