"""
Cash reports in A4 - the closing report of a till session (figures from cash_report_service). Internal documents,
not fiscal ones. Same identity as the invoices: the company box and the logo come from pdf_generator.
"""
import io
from datetime import datetime, timedelta, timezone

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.utils.pdf_generator import (
    ACCENT, BORDER, TABLE_HEADER_BG, TABLE_ROW_ALT, TEXT_MUTED, TEXT_PRIMARY,
    _draw_company_box, _resolve_logo_path, _wrap_to_width,
)

LUANDA = timezone(timedelta(hours=1))  # Angola: UTC+1 all year, no daylight saving
PAGE_W, PAGE_H = A4
MARGIN = 15 * mm
CONTENT_W = PAGE_W - 2 * MARGIN
SUCCESS = HexColor("#2E7D4F")


def kz(value: float, signed: bool = False) -> str:
    s = f"{value:+,.2f}" if signed else f"{value:,.2f}"
    return s.replace(",", " ").replace(".", ",") + " Kz"


def _when(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            value = value.astimezone(LUANDA)
        return value.strftime("%d/%m/%Y %H:%M")
    return value.strftime("%d/%m/%Y")


class _Page:
    """Keeps the current height and opens a new page when a block would not fit."""

    def __init__(self, c):
        self.c, self.y = c, PAGE_H - MARGIN

    def need(self, height: float) -> None:
        if self.y - height < 25 * mm:
            self.c.showPage()
            self.y = PAGE_H - MARGIN


def _section_title(p: _Page, title: str) -> None:
    p.need(14 * mm)
    c = p.c
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 10.5)
    c.drawString(MARGIN, p.y, title)
    p.y -= 2 * mm
    c.setStrokeColor(ACCENT)
    c.setLineWidth(0.6)
    c.line(MARGIN, p.y, MARGIN + CONTENT_W, p.y)
    p.y -= 5 * mm


def _table(p: _Page, headers, rows, widths, aligns, total=None) -> None:
    """A plain table: header row, striped rows, optional bold total row."""
    c, row_h = p.c, 6 * mm
    xs = [MARGIN]
    for w in widths[:-1]:
        xs.append(xs[-1] + w * CONTENT_W)

    def draw_row(values, font, fill=None):
        p.need(row_h)
        if fill is not None:
            c.setFillColor(fill)
            c.rect(MARGIN, p.y - row_h + 1.5 * mm, CONTENT_W, row_h, fill=1, stroke=0)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont(font, 9)
        for i, value in enumerate(values):
            if aligns[i] == "r":
                c.drawRightString(xs[i] + widths[i] * CONTENT_W - 2 * mm, p.y - 2.5 * mm, value)
            else:
                c.drawString(xs[i] + 2 * mm, p.y - 2.5 * mm, value)
        p.y -= row_h

    draw_row(headers, "Helvetica-Bold", TABLE_HEADER_BG)
    if not rows:
        draw_row(["Nenhum"] + [""] * (len(headers) - 1), "Helvetica-Oblique")
    for i, row in enumerate(rows):
        draw_row(row, "Helvetica", TABLE_ROW_ALT if i % 2 else None)
    if total is not None:
        draw_row(total, "Helvetica-Bold", HexColor("#D8D8D8"))
    p.y -= 4 * mm


def generate_closing_report_pdf(data: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Relatorio de fecho - {data['pos_name']} - {_when(data['business_date'])}")
    p = _Page(c)
    s = data["summary"]

    # header: logo, title, the session; then the company box and the session details side by side
    logo = _resolve_logo_path(data["company"])
    if logo:
        c.drawImage(ImageReader(logo), MARGIN, p.y - 18 * mm, width=40 * mm, height=18 * mm,
                    preserveAspectRatio=True, anchor="w", mask="auto")
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(MARGIN + CONTENT_W, p.y - 6 * mm, "RELATÓRIO DE FECHO DE CAIXA")
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 10)
    c.drawRightString(MARGIN + CONTENT_W, p.y - 12 * mm, f"{data['pos_name']}  ·  {data['activity_name']}")
    c.drawRightString(MARGIN + CONTENT_W, p.y - 17 * mm, f"Dia comercial {_when(data['business_date'])}")
    p.y -= 24 * mm

    box_h = _draw_company_box(c, MARGIN, p.y, 95 * mm, data["company"])
    details = [
        ("Abertura", f"{_when(data['opened_at'])}  ·  {data['opened_by']}"),
        ("Fecho", f"{_when(data['closed_at'])}  ·  {data['closed_by']}"),
        ("Impresso em", _when(datetime.now(LUANDA))),
    ]
    dy = p.y - 6 * mm
    for label, value in details:
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN + 100 * mm, dy, label + ":")
        c.setFont("Helvetica", 9)
        c.drawString(MARGIN + 122 * mm, dy, value[:40])
        dy -= 5.5 * mm
    p.y -= max(box_h, 20 * mm) + 8 * mm

    _section_title(p, "Recebimentos por modo de pagamento")
    _table(p, ["Modo de pagamento", "Na gaveta", "Valor"],
           [[m["name"], "Sim" if m["is_cash"] else "Não", kz(m["amount"])] for m in s["by_method"]],
           [0.55, 0.15, 0.30], ["l", "l", "r"], total=["Total recebido", "", kz(s["total_received"])])

    _section_title(p, "Documentos emitidos")
    _table(p, ["Tipo de documento", "Quantidade", "Total"],
           [[d["label"], str(d["count"]), kz(d["total"])] for d in data["documents"]],
           [0.55, 0.15, 0.30], ["l", "r", "r"])

    _section_title(p, "Fecho da caixa")
    lines = [
        ("Fundo de abertura", kz(s["opening_amount"]), False),
        ("+ Numerário recebido", kz(s["cash_sales"]), False),
        ("+ Transferências recebidas", kz(s["transfers_in"]), False),
        ("+ Entradas", kz(s["entries"]), False),
        ("- Transferências enviadas", kz(s["transfers_out"]), False),
        ("- Saídas", kz(s["exits"]), False),
        ("Esperado na gaveta", kz(s["expected_cash"]), True),
        ("Contado", kz(data["counted"]), True),
    ]
    for label, value, bold in lines:
        p.need(6 * mm)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", 9.5)
        c.drawString(MARGIN + 2 * mm, p.y, label)
        c.drawRightString(MARGIN + 110 * mm, p.y, value)
        p.y -= 5.8 * mm
    diff = data["difference"]
    p.need(8 * mm)
    c.setFillColor(SUCCESS if diff == 0 else ACCENT)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(MARGIN + 2 * mm, p.y, "Diferença" + ("" if diff == 0 else (" (excedente)" if diff > 0 else " (falta)")))
    c.drawRightString(MARGIN + 110 * mm, p.y, kz(diff, signed=diff != 0))
    p.y -= 7 * mm
    if data["notes"]:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN + 2 * mm, p.y, "Motivo:")
        c.setFont("Helvetica", 9)
        for part in _wrap_to_width(c, data["notes"], "Helvetica", 9, CONTENT_W - 22 * mm):
            p.need(5 * mm)
            c.drawString(MARGIN + 18 * mm, p.y, part)
            p.y -= 5 * mm
    if s["pending_in"]:
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica-Oblique", 8.5)
        c.drawString(MARGIN + 2 * mm, p.y, f"Transferências por receber (fora da gaveta): {kz(s['pending_in'])}")
        p.y -= 6 * mm

    # signatures
    p.need(30 * mm)
    p.y -= 16 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    for x, label, name in ((MARGIN, "O(A) Caixa", data["closed_by"]), (MARGIN + CONTENT_W / 2 + 5 * mm, "O(A) Responsável", "")):
        c.line(x, p.y, x + CONTENT_W / 2 - 10 * mm, p.y)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(x, p.y - 4.5 * mm, label + (f"  ·  {name}" if name else ""))

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawCentredString(PAGE_W / 2, 12 * mm, "Documento interno de controlo de caixa - sem valor fiscal")
    c.showPage()
    c.save()
    return buffer.getvalue()
