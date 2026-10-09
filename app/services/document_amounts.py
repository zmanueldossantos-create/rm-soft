"""
The amounts of a document once its global discount is spread over its lines - what the SAF-T and the AGT API
declare (each line's amount "excluding taxes, the discounts deducted", and its share of the global discount), and
what the invoice prints.

A document stores its lines before the global discount, and its total after it: total = (subtotal + VAT) x (1 - p).
The discount is spread over the lines in proportion to their amount; the VAT of each line is taken on its net. The
rounding cents left over go to the largest line, so the sum always lands on the stored total - an issued document
never changes, only the way its amounts are shown.
"""


def split_global_discount(lines: list[tuple[float, float]], discount_percent: float, stored_total: float) -> dict:
    """
    lines: (amount before the global discount, VAT rate in %) for each line, in the document's order.
    Returns {"lines": [{"settlement", "net", "vat"} ...], "net_total", "tax_total", "gross_total", "discount_total"}.
    """
    pct = float(discount_percent or 0) / 100
    out = []
    for amount, rate in lines:
        settlement = round(amount * pct, 2)
        net = round(amount - settlement, 2)
        out.append({"settlement": settlement, "net": net, "vat": round(net * rate / 100, 2), "rate": rate})

    if out and pct:
        # the rounding cents left over go to the largest line, so the document lands on its stored total
        gap = round(stored_total - sum(l["net"] + l["vat"] for l in out), 2)
        if gap:
            big = max(out, key=lambda l: l["net"])
            share = round(gap / (1 + big["rate"] / 100), 2)
            big["net"] = round(big["net"] + share, 2)
            big["settlement"] = round(big["settlement"] - share, 2)
            big["vat"] = round(big["vat"] + gap - share, 2)

    net_total = round(sum(l["net"] for l in out), 2)
    tax_total = round(sum(l["vat"] for l in out), 2)
    return {
        "lines": [{k: l[k] for k in ("settlement", "net", "vat")} for l in out],
        "net_total": net_total,
        "tax_total": tax_total,
        "gross_total": round(net_total + tax_total, 2),
        "discount_total": round(sum(l["settlement"] for l in out), 2),
    }
