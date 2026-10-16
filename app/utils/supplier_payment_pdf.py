"""
The supplier payment voucher (Comprovativo de pagamento PAG2026/1: the invoices it settles) and the supplier's conta
corrente (its documents with the running balance) in A4 - same identity as the other A4 reports.
"""
import io
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import LUANDA, MARGIN, _Page, _draw_header, _section_title, _table, _when, kz
from app.utils.pdf_generator import TEXT_MUTED


def _day(value) -> str:
    return value.strftime("%d/%m/%Y") if isinstance(value, (date, datetime)) else (value or "-")


def _footer(c) -> None:
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, MARGIN, f"Documento interno - não serve de fatura nem de recibo  ·  impresso em {_when(datetime.now(LUANDA))}")


def generate_supplier_payment_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Pagamento {data['reference']}")
    p = _Page(c)
    supplier = data["supplier_name"] + (f"  ·  NIF {data['supplier_nif']}" if data.get("supplier_nif") else "")
    details = [("Fornecedor", supplier), ("Data", _day(data["payment_date"])), ("Método", data["method"] or "-")]
    if data.get("source"):
        details.append(("Saída de", data["source"]))
    if data.get("reference_text"):
        details.append(("Referência", data["reference_text"]))
    state = "ANULADO" if data["status"] == "ANULADO" else "Original"
    _draw_header(p, company, "PAGAMENTO A FORNECEDOR", [data["reference"], state], details)
    _section_title(p, "Faturas pagas")
    rows = [[a["reference"], a["supplier_document"], _day(a["document_date"]), kz(a["invoice_total"]), kz(a["amount"])]
            for a in data["allocations"]]
    _table(p, ["Registo", "Documento do fornecedor", "Data", "Total da fatura", "Pago"], rows,
           [0.16, 0.32, 0.14, 0.19, 0.19], ["l", "l", "l", "r", "r"], total=["", "Total pago", "", "", kz(data["amount"])])
    for text in ([f"Observações: {data['notes']}"] if data.get("notes") else []) + (
            [f"Anulado em {_when(data['cancelled_at'])}: {data['cancel_reason']}"] if data["status"] == "ANULADO" else []):
        p.need(10 * mm)
        p.y -= 6 * mm
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, p.y, text[:140])
    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()


def generate_supplier_statement_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Conta corrente {data['supplier_name']}")
    p = _Page(c)
    period = f"{_day(data['date_from']) if data['date_from'] else 'início'} a {_day(data['date_to']) if data['date_to'] else 'hoje'}"
    details = [("Fornecedor", data["supplier_name"]), ("NIF", data.get("supplier_nif") or "-"), ("Período", period),
               ("Saldo anterior", kz(data["opening_balance"])), ("Saldo final", kz(data["closing_balance"]))]
    _draw_header(p, company, "CONTA CORRENTE", ["Fornecedor", _day(datetime.now(LUANDA))], details)
    _section_title(p, "Movimentos (saldo = valor em dívida ao fornecedor)")
    rows = [[_day(l["date"]), l["document"], l["description"], kz(l["debit"]) if l["debit"] else "",
             kz(l["credit"]) if l["credit"] else "", kz(l["balance"])] for l in data["lines"]]
    _table(p, ["Data", "Documento", "Descrição", "Débito", "Crédito", "Saldo"], rows,
           [0.12, 0.2, 0.26, 0.14, 0.14, 0.14], ["l", "l", "l", "r", "r", "r"],
           total=["", "Totais", "", kz(data["total_debit"]), kz(data["total_credit"]), kz(data["closing_balance"])])
    _footer(c)
    c.showPage()
    c.save()
    return buffer.getvalue()
