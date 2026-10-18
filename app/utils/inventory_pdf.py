"""
The inventory of a warehouse in A4 (stock_inventory_service): a counting sheet while it is a draft (empty Contado
column to fill in by hand), the record of the count once validated (expected, counted, difference, value). Internal
document, same identity as the cash reports.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import CONTENT_W, LUANDA, MARGIN, _Page, _draw_header, _section_title, _table, _when, kz
from app.utils.pdf_generator import BORDER, TEXT_MUTED


def _qty(value) -> str:
    if value is None:
        return ""
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def generate_inventory_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    validated = data["status"] == "VALIDADO"
    c.setTitle(f"Inventário {data['reference']} - {data['warehouse_name']}")
    p = _Page(c)
    details = [("Período", data["period_label"]), ("Criado", f"{_when(data['created_at'])}  ·  {data['created_by'] or '-'}")]
    if validated:
        details.append(("Validado", f"{_when(data['validated_at'])}  ·  {data['validated_by'] or '-'}"))
    details.append(("Impresso em", _when(datetime.now(LUANDA))))
    _draw_header(p, company, "INVENTÁRIO" if validated else "FOLHA DE CONTAGEM",
                 [f"{data['reference']}  ·  {data['warehouse_name']}", "Validado" if validated else "Em curso"], details)

    def unit(line):
        return f" {line['unit_code']}" if line["unit_code"] else ""

    # emplacements (optional): a first column "Local." when the warehouse has them - the lines come sorted by it
    located = any(l.get("location_code") for l in data["lines"])

    def with_location(headers, rows, widths, aligns, total=None):
        if not located:
            return headers, rows, widths, aligns, total
        scale = 0.88  # the other columns give 12 % to the location
        return (["Local."] + headers, [[l.get("location_code") or ""] + r for l, r in zip(data["lines"], rows)],
                [0.12] + [w * scale for w in widths], ["l"] + aligns, ([""] + total) if total else None)

    if validated:
        _section_title(p, "Contagem")
        rows = [[l["code"], l["name"], _qty(l["expected"]) + unit(l),
                 (_qty(l["counted"]) + unit(l)) if l["counted"] is not None else "não contado",
                 _qty(l["difference"]) if l["difference"] else ("0" if l["difference"] == 0 else ""),
                 kz(l["difference_value"]) if l["difference_value"] else ""]
                for l in data["lines"]]
        headers, rows, widths, aligns, total = with_location(
            ["Código", "Produto", "Esperado", "Contado", "Diferença", "Valor"], rows,
            [0.13, 0.32, 0.14, 0.14, 0.12, 0.15], ["l", "l", "r", "r", "r", "r"],
            ["", f"{data['summary']['differences']} diferença(s)", "", "", "", kz(data["summary"]["difference_value"])])
        _table(p, headers, rows, widths, aligns, total=total)
    else:
        _section_title(p, "Produtos a contar")
        rows = [[l["code"], l["name"], (l["unit_code"] or ""), "", ""] for l in data["lines"]]
        headers, rows, widths, aligns, _ = with_location(
            ["Código", "Produto", "Unidade", "Contado", "Observações"], rows,
            [0.14, 0.40, 0.10, 0.16, 0.20], ["l", "l", "l", "r", "l"])
        _table(p, headers, rows, widths, aligns)

    p.need(30 * mm)
    p.y -= 16 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    for x, label in ((MARGIN, "Contado por"), (MARGIN + CONTENT_W / 2 + 5 * mm, "Verificado por")):
        c.line(x, p.y, x + CONTENT_W / 2 - 10 * mm, p.y)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, p.y - 4.5 * mm, label)
    c.showPage()
    c.save()
    return buffer.getvalue()
