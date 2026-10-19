"""
The Farmácia's registers in A4 (pharmacy_register_service): the traceability of a lot, the registo de receitas and the
registo de psicotrópicos e estupefacientes. Internal documents, the same identity as the cash reports; landscape, the
registers have many columns.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import LUANDA, _draw_header, _when
from app.utils.pdf_generator import ACCENT, BORDER, TABLE_HEADER_BG, TABLE_ROW_ALT, TEXT_MUTED, TEXT_PRIMARY, _fit_text

PAGE_W, PAGE_H = landscape(A4)
MARGIN = 12 * mm
CONTENT_W = PAGE_W - 2 * MARGIN


class _Page:
    """The current height on a landscape page; a new page when a block would not fit."""

    def __init__(self, c):
        self.c, self.y = c, PAGE_H - MARGIN

    def need(self, height: float) -> None:
        if self.y - height < 18 * mm:
            self.c.showPage()
            self.y = PAGE_H - MARGIN


def _qty(value) -> str:
    if value is None:
        return ""
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def _day(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        value = value.astimezone(LUANDA) if value.tzinfo else value
    return value.strftime("%d/%m/%Y")


def _title(p: _Page, text: str) -> None:
    p.need(14 * mm)
    c = p.c
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(MARGIN, p.y, text)
    p.y -= 2 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.6)
    c.line(MARGIN, p.y, MARGIN + CONTENT_W, p.y)
    p.y -= 5 * mm


def _table(p: _Page, headers, rows, widths, aligns, size: float = 7.5, total=None) -> None:
    """Header, striped rows (each cell cut to its column), optional bold total row - repeated header on a new page."""
    c, row_h = p.c, 5.2 * mm
    xs = [MARGIN]
    for w in widths[:-1]:
        xs.append(xs[-1] + w * CONTENT_W)

    def draw(values, font, fill=None):
        if fill is not None:
            c.setFillColor(fill)
            c.rect(MARGIN, p.y - row_h + 1.5 * mm, CONTENT_W, row_h, fill=1, stroke=0)
        c.setFillColor(TEXT_PRIMARY)
        for i, value in enumerate(values):
            width = widths[i] * CONTENT_W - 3 * mm
            text = _fit_text(c, str(value or ""), font, size, width)
            c.setFont(font, size)
            if aligns[i] == "r":
                c.drawRightString(xs[i] + widths[i] * CONTENT_W - 1.5 * mm, p.y - 2.2 * mm, text)
            else:
                c.drawString(xs[i] + 1.5 * mm, p.y - 2.2 * mm, text)
        p.y -= row_h

    def header():
        p.need(row_h * 2)
        draw(headers, "Helvetica-Bold", TABLE_HEADER_BG)

    header()
    if not rows:
        draw(["Nenhum movimento"] + [""] * (len(headers) - 1), "Helvetica-Oblique")
    for i, row in enumerate(rows):
        if p.y - row_h < 18 * mm:
            p.need(row_h * 2)
            header()
        draw(row, "Helvetica", TABLE_ROW_ALT if i % 2 else None)
    if total is not None:
        p.need(row_h)
        draw(total, "Helvetica-Bold", TABLE_HEADER_BG)
    c.setStrokeColor(BORDER)
    p.y -= 4 * mm


def _start(title: str, doc_title: str, company: dict, right: list[str], details: list[tuple[str, str]]):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=landscape(A4))
    c.setTitle(doc_title)
    p = _Page(c)
    _draw_header(p, company, title, right, details + [("Impresso em", _when(datetime.now(LUANDA)))],
                 margin=MARGIN, content_w=CONTENT_W)
    return buffer, c, p


def _finish(buffer, c) -> bytes:
    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_lot_trace_pdf(data: dict, company: dict) -> bytes:
    buffer, c, p = _start("RASTREABILIDADE DE LOTE", f"Lote {data['label']} - {data['product_name']}", company,
                          [f"{data['product_code']} · {data['product_name']}", data["label"]],
                          [("Vendido", _qty(data["sold_total"])), ("Em stock", _qty(data["remaining_total"]))])
    _title(p, "Movimentos do lote")
    rows = [[_day(m["date"]), m["type"], m["reference"] or "-", m["warehouse"], m["detail"], m["prescription"] or "",
             _qty(m["quantity_in"]), _qty(m["quantity_out"])] for m in data["movements"]]
    _table(p, ["Data", "Movimento", "Documento", "Armazém", "Cliente / origem / motivo", "Receita", "Entrada", "Saída"],
           rows, [0.08, 0.10, 0.13, 0.15, 0.27, 0.09, 0.09, 0.09], ["l", "l", "l", "l", "l", "l", "r", "r"])
    _title(p, "Em stock")
    _table(p, ["Armazém", "Quantidade"], [[r["warehouse"], _qty(r["quantity"])] for r in data["remaining"]],
           [0.5, 0.5], ["l", "r"])
    return _finish(buffer, c)


def generate_prescriptions_pdf(entries: list[dict], company: dict, date_from, date_to) -> bytes:
    period = f"{_day(date_from)} a {_day(date_to)}"
    buffer, c, p = _start("REGISTO DE RECEITAS", "Registo de receitas " + period, company, [period],
                          [("Receitas", str(len(entries)))])
    rows = []
    for e in entries:
        medicines = "; ".join(i["product_name"] + " " + _qty(i["quantity"]) + (" " + i["unit"] if i["unit"] else "")
                              + (" (" + ", ".join(i["lots"]) + ")" if i["lots"] else "") for i in e["items"])
        patient = (e["patient_name"] or "") + (f" · {e['patient_document']}" if e["patient_document"] else "")
        rows.append([_day(e["date"]), e["reference"], ("Especial " if e["is_special"] else "") + (e["number"] or "-"),
                     e["prescriber"] or "", e["health_unit"] or "", patient, medicines])
    _table(p, ["Data", "Documento", "N.º receita", "Médico", "Unidade de saúde", "Utente", "Medicamentos (quantidade, lote)"],
           rows, [0.07, 0.11, 0.10, 0.13, 0.13, 0.15, 0.31], ["l"] * 7, size=7)
    return _finish(buffer, c)


def generate_psychotropics_pdf(products: list[dict], company: dict, date_from, date_to) -> bytes:
    period = f"{_day(date_from)} a {_day(date_to)}"
    buffer, c, p = _start("REGISTO DE PSICOTRÓPICOS E ESTUPEFACIENTES", "Registo de psicotrópicos " + period, company,
                          [period], [("Produtos", str(len(products)))])
    if not products:
        _title(p, "Nenhum medicamento de receita especial com stock ou movimentos no período")
    for product in products:
        name = f"{product['product_code']} · {product['product_name']}"
        if product.get("active_substance"):
            name += f" ({product['active_substance']}{' ' + product['dosage'] if product.get('dosage') else ''})"
        _title(p, name)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawString(MARGIN, p.y, f"Stock inicial {_qty(product['opening'])}  ·  Entradas {_qty(product['total_in'])}  ·  "
                                  f"Saídas {_qty(product['total_out'])}  ·  Stock final {_qty(product['closing'])}")
        p.y -= 5 * mm
        rows = [[_day(l["date"]), l["type"], l["reference"] or "-", l["detail"], l["prescription"] or "",
                 (l["patient"] or "") + (f" · {l['patient_document']}" if l["patient_document"] else ""),
                 ", ".join(l["lots"]), _qty(l["quantity_in"]), _qty(l["quantity_out"]), _qty(l["balance"])]
                for l in product["lines"]]
        _table(p, ["Data", "Movimento", "Documento", "Fornecedor / cliente / motivo", "Receita", "Utente · documento", "Lote",
                   "Entrada", "Saída", "Saldo"], rows,
               [0.07, 0.08, 0.11, 0.19, 0.08, 0.15, 0.12, 0.066, 0.066, 0.068], ["l"] * 7 + ["r", "r", "r"], size=7,
               total=["", "", "", "Totais do período", "", "", "", _qty(product["total_in"]),
                      _qty(product["total_out"]), _qty(product["closing"])])
    # the pharmacist's signature, as an inspection asks
    p.need(25 * mm)
    p.y -= 14 * mm
    c.setStrokeColor(BORDER)
    c.line(MARGIN, p.y, MARGIN + 80 * mm, p.y)
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 8.5)
    c.drawString(MARGIN, p.y - 4.5 * mm, "O diretor técnico (farmacêutico responsável)")
    return _finish(buffer, c)
