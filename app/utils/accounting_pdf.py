"""
Contabilidade in A4: the balancete and the extrato de conta (figures from accounting_reports_service). Internal
documents, with the company box and the logo of the invoices.
"""
import io
from datetime import datetime

from reportlab.lib.colors import HexColor
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import CONTENT_W, LUANDA, MARGIN, _draw_header, _fit, _Page, _section_title, _when
from app.utils.pdf_generator import TABLE_HEADER_BG, TABLE_ROW_ALT, TEXT_MUTED, TEXT_PRIMARY

ROW_H = 5.5 * mm
SIZE = 8


def _amount(value) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",") if value else ""


def _side(value) -> str:
    return f"{_amount(abs(value))} {'D' if value > 0 else 'C'}" if value else ""


def _day(value) -> str:
    return value.strftime("%d/%m/%Y")


def _footer(c) -> None:
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, MARGIN, f"Documento interno de contabilidade  ·  impresso em {_when(datetime.now(LUANDA))}  ·  "
                                 f"página {c.getPageNumber()}")


def _table(p: _Page, headers, rows, widths, aligns, bold_rows=(), total=None) -> None:
    """Rows cut to their column, the header repeated on every new page."""
    c = p.c
    xs = [MARGIN]
    for w in widths[:-1]:
        xs.append(xs[-1] + w * CONTENT_W)

    def draw(values, font, fill=None):
        c.setFont(font, SIZE)
        if fill is not None:
            c.setFillColor(fill)
            c.rect(MARGIN, p.y - ROW_H + 1.3 * mm, CONTENT_W, ROW_H, fill=1, stroke=0)
        c.setFillColor(TEXT_PRIMARY)
        for i, value in enumerate(values):
            width = widths[i] * CONTENT_W - 3 * mm
            text = _fit(c, str(value), font, SIZE, width)
            if aligns[i] == "r":
                c.drawRightString(xs[i] + widths[i] * CONTENT_W - 1.5 * mm, p.y - 2.3 * mm, text)
            else:
                c.drawString(xs[i] + 1.5 * mm, p.y - 2.3 * mm, text)
        p.y -= ROW_H

    def header():
        draw(headers, "Helvetica-Bold", TABLE_HEADER_BG)

    header()
    if not rows:
        draw(["Nenhum movimento"] + [""] * (len(headers) - 1), "Helvetica-Oblique")
    for i, row in enumerate(rows):
        if p.y - ROW_H < 25 * mm:
            _footer(c)
            c.showPage()
            p.y = A4[1] - MARGIN
            header()
        draw(row, "Helvetica-Bold" if i in bold_rows else "Helvetica", TABLE_ROW_ALT if i % 2 else None)
    if total is not None:
        p.need(ROW_H)
        draw(total, "Helvetica-Bold", HexColor("#D8D8D8"))


def generate_trial_balance_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle("Balancete")
    p = _Page(c)
    period = f"{_day(data['date_from'])} a {_day(data['date_to'])}"
    _draw_header(p, company, "BALANCETE", [period], [("Período", period), ("Contas", str(len(data["accounts"])))])
    _section_title(p, "Saldos e movimentos por conta (D devedor, C credor)")
    rows, bold = [], []
    for i, a in enumerate(data["accounts"]):
        rows.append([a["code"], ("  " * (a["level"] - 1)) + a["name"], _side(a["opening"]), _amount(a["debit"]),
                     _amount(a["credit"]), _side(a["closing"])])
        if a["level"] == 1:
            bold.append(i)
    t = data["totals"]
    _table(p, ["Conta", "Descrição", "Saldo inicial", "Débito", "Crédito", "Saldo final"], rows,
           [0.11, 0.33, 0.14, 0.14, 0.14, 0.14], ["l", "l", "r", "r", "r", "r"], bold_rows=bold,
           total=["", "Totais", _side(t["opening"]), _amount(t["debit"]), _amount(t["credit"]), _side(t["closing"])])
    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_account_ledger_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    account = data["account"]
    c.setTitle(f"Extrato {account['code']}")
    p = _Page(c)
    period = f"{_day(data['date_from'])} a {_day(data['date_to'])}"
    _draw_header(p, company, "EXTRATO DE CONTA", [period], [
        ("Conta", f"{account['code']} - {account['name']}"), ("Período", period),
        ("Saldo inicial", _side(data["opening"]) or "0,00"), ("Saldo final", _side(data["closing"]) or "0,00")])
    _section_title(p, "Movimentos")
    rows = [[_day(l["date"]), l["entry"], l["account_code"], l["description"], _amount(l["debit"]), _amount(l["credit"]),
             _side(l["balance"])] for l in data["lines"]]
    _table(p, ["Data", "Lançamento", "Conta", "Descrição", "Débito", "Crédito", "Saldo"], rows,
           [0.1, 0.13, 0.1, 0.27, 0.13, 0.13, 0.14], ["l", "l", "l", "l", "r", "r", "r"],
           total=["", "", "", "Totais", _amount(data["total_debit"]), _amount(data["total_credit"]), _side(data["closing"])])
    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()
