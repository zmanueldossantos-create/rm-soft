"""The global discount of a document spread over its lines: each line's net and VAT after the discount, the totals
landing exactly on the stored total - the amounts the SAF-T, the AGT API and the invoice declare."""
from app.services.document_amounts import split_global_discount


def test_fr2026_7_one_line_ten_percent():
    s = split_global_discount([(600.0, 14.0)], 10, 615.60)
    assert s["lines"] == [{"settlement": 60.0, "net": 540.0, "vat": 75.6}]
    assert (s["net_total"], s["tax_total"], s["gross_total"], s["discount_total"]) == (540.0, 75.6, 615.6, 60.0)


def test_no_discount_changes_nothing():
    s = split_global_discount([(4000.0, 14.0), (300.0, 0.0)], 0, 4860.0)
    assert [l["net"] for l in s["lines"]] == [4000.0, 300.0] and s["discount_total"] == 0
    assert s["gross_total"] == 4860.0


def test_several_rates_and_an_exempt_line_land_on_the_stored_total():
    lines = [(1333.33, 14.0), (777.77, 5.0), (95.55, 0.0)]
    subtotal = sum(a for a, _ in lines)
    vat = round(1333.33 * 0.14, 2) + round(777.77 * 0.05, 2)
    stored = round(subtotal + vat - round((subtotal + vat) * 0.075, 2), 2)  # as create_invoice computes it
    s = split_global_discount(lines, 7.5, stored)
    assert s["gross_total"] == stored
    assert s["lines"][2]["vat"] == 0  # the exempt line never gets VAT, even from the rounding
    assert all(l["net"] >= 0 and l["settlement"] >= 0 for l in s["lines"])
