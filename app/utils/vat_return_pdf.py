"""
The apuramento do IVA of a month in A4 (vat_return_service): the VAT charged on sales and the VAT deductible on
purchases, by rate, and the result - for the accountant. Internal document, same identity as the cash reports.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import LUANDA, _Page, _draw_header, _section_title, _table, _when, kz


def _rate(line: dict) -> str:
    text = f"{line['tax_code']} {line['rate']:g} %"
    return text + (f" · {line['exemption_code']}" if line.get("exemption_code") else "")


def generate_vat_return_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Apuramento do IVA - {data['period_label']}")
    p = _Page(c)
    _draw_header(p, company, "APURAMENTO DO IVA", [data["period_label"], data["regime_name"] or "Sem regime"], [
        ("Período", f"{data['date_from'].strftime('%d/%m/%Y')} a {data['date_to'].strftime('%d/%m/%Y')}"),
        ("Regime", f"{data['regime_name'] or '-'}  ·  dedutível {data['input_vat_deductible_pct']:g} %"
                   + (f"  ·  {data['turnover_vat_pct']:g} % do volume de negócios" if data["turnover_vat_pct"] else "")),
        ("Impresso em", _when(datetime.now(LUANDA))),
    ])

    _section_title(p, "IVA liquidado (vendas)")
    _table(p, ["Taxa", "Documentos", "Base", "IVA"],
           [[_rate(l), str(l["documents"]), kz(l["base"]), kz(l["vat"])] for l in data["sales"]] or [["Sem vendas", "", "", ""]],
           [0.40, 0.16, 0.22, 0.22], ["l", "r", "r", "r"], total=["Total", "", kz(data["sales_base"]), kz(data["output_vat"])])

    _section_title(p, "IVA dedutível (compras)")
    _table(p, ["Taxa", "Documentos", "Base", "IVA suportado", "Dedutível"],
           [[_rate(l), str(l["documents"]), kz(l["base"]), kz(l["vat"]), kz(l["deductible"])] for l in data["purchases"]]
           or [["Sem compras", "", "", "", ""]],
           [0.30, 0.13, 0.19, 0.19, 0.19], ["l", "r", "r", "r", "r"],
           total=["Total", "", kz(data["purchases_base"]), kz(data["input_vat"]), kz(data["deductible_vat"])])

    _section_title(p, "Apuramento")
    rows = [["IVA liquidado", kz(data["output_vat"])]]
    if data["turnover_vat_pct"]:
        rows.append([f"IVA sobre o volume de negócios ({data['turnover_vat_pct']:g} % de {kz(data['sales_base'])})", kz(data["turnover_vat"])])
    rows.append(["IVA dedutível", kz(-data["deductible_vat"])])
    if data["no_return"]:
        label, value = "Sem apuramento de IVA neste regime", kz(0)
    elif data["result"] >= 0:
        label, value = "IVA a pagar", kz(data["to_pay"])
    else:
        label, value = "Crédito de IVA", kz(data["credit"])
    _table(p, ["", "Valor"], rows, [0.70, 0.30], ["l", "r"], total=[label, value])

    c.showPage()
    c.save()
    return buffer.getvalue()
