"""
The production list of a day (Encomendas): what the workshop must make for the orders to deliver that day - the
total of each article first, then each order with its hour, customer, delivery and the production notes of its lines.
Internal document, same identity as the cash reports.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import CONTENT_W, LUANDA, MARGIN, _Page, _draw_header, _section_title, _table, _when
from app.utils.pdf_generator import TEXT_MUTED, TEXT_PRIMARY


def _qty(value: float) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def _cut(text: str, length: int) -> str:
    text = text or ""
    return text if len(text) <= length else text[:length - 1] + "…"


def generate_production_list_pdf(data: dict, company: dict) -> bytes:
    """data: {day (date), totals: [{name, quantity, unit}], orders: [order dicts of customer_order_service]}."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    day = data["day"].strftime("%d/%m/%Y")
    c.setTitle(f"Lista de produção {day}")
    p = _Page(c)
    _draw_header(p, company, "LISTA DE PRODUÇÃO", [f"Entregas de {day}", f"{len(data['orders'])} encomenda(s)"],
                 [("Entregas", day), ("Impresso em", _when(datetime.now(LUANDA)))])

    _section_title(p, "A produzir")
    _table(p, ["Artigo", "Quantidade"], [[_cut(t["name"], 70), _qty(t["quantity"]) + (f" {t['unit']}" if t.get("unit") else "")]
                                         for t in data["totals"]], [0.75, 0.25], ["l", "r"])

    _section_title(p, "Encomendas")
    for order in data["orders"]:
        when = order["delivery_at"].astimezone(LUANDA).strftime("%H:%M")
        how = f"Entrega: {order['delivery_address']}" if order["delivery_mode"] == "ENTREGA" else "Levanta na loja"
        contact = order.get("contact_phone") or order.get("customer_phone") or ""
        lines = len(order["lines"])
        p.need((10 + 5 * lines) * mm)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 10)
        c.drawString(MARGIN, p.y - 3 * mm, _cut(f"{when}  ·  {order['reference']}  ·  {order['customer_name']}", 90))
        c.setFont("Helvetica", 8.5)
        c.setFillColor(TEXT_MUTED)
        c.drawRightString(MARGIN + CONTENT_W, p.y - 3 * mm, _cut(f"{how}  {contact}".strip(), 70))
        p.y -= 7 * mm
        for line in order["lines"]:
            c.setFillColor(TEXT_PRIMARY)
            c.setFont("Helvetica", 9.5)
            c.drawString(MARGIN + 4 * mm, p.y - 2 * mm, _cut(f"{_qty(line['quantity'])} × {line['description']}", 60))
            if line.get("production_note"):
                c.setFont("Helvetica-Oblique", 9.5)
                c.drawString(MARGIN + 95 * mm, p.y - 2 * mm, _cut("«" + line["production_note"] + "»", 55))
            p.y -= 5 * mm
        if order.get("notes"):
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica-Oblique", 8.5)
            c.drawString(MARGIN + 4 * mm, p.y - 2 * mm, _cut(order["notes"], 110))
            p.y -= 5 * mm
        p.y -= 3 * mm
    if not data["orders"]:
        c.setFont("Helvetica-Oblique", 9.5)
        c.setFillColor(TEXT_MUTED)
        c.drawString(MARGIN, p.y - 3 * mm, "Nenhuma encomenda para entregar neste dia.")
    c.showPage()
    c.save()
    return buffer.getvalue()
