"""
A guide in A4 (goods_movement_service): Guia de Remessa / Transporte / Devolução - who receives the goods, where they
are loaded and unloaded, when the transport starts, the vehicle, the lines; ATCUD and hash (simulated until the AGT
homologation, like the invoices). Same identity as the other A4 documents.
"""
import io
from datetime import datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.utils.cash_report_pdf import LUANDA, MARGIN, _Page, _draw_header, _section_title, _table, _when, kz
from app.utils.pdf_generator import TEXT_MUTED

PARTY_LABEL = {"GR": "Cliente", "GT": "Armazém de destino", "GD": "Fornecedor"}


def _qty(value: float) -> str:
    text = f"{value:,.3f}".rstrip("0").rstrip(".")
    return text.replace(",", " ").replace(".", ",")


def generate_guia_pdf(data: dict, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"{data['type_label']} {data['reference']}")
    p = _Page(c)
    party = data["party"] or "-"
    if data.get("party_nif"):
        party += f"  ·  NIF {data['party_nif']}"
    details = [
        (PARTY_LABEL[data["movement_type"]], party),
        # the warehouse, then its address when it has one (the address is the warehouse's name otherwise)
        ("Carga", data["origin_warehouse"] if data["load_address"] in (None, "", data["origin_warehouse"])
         else f"{data['origin_warehouse'] or ''} - {data['load_address']}".strip(" -")),
        ("Descarga", data["unload_address"]),
        ("Transporte", _when(data["start_time"])),
        ("Viatura", data["vehicle_plate"] or "-"),
    ]
    if data.get("purchase_invoice"):
        details.append(("Fatura de compra", data["purchase_invoice"]))
    details.append(("ATCUD", data["atcud"]))
    state = {"EMITIDA": "Original", "FATURADA": "Faturada", "ANULADA": "ANULADA"}[data["status"]]
    _draw_header(p, company, data["type_label"].upper(), [data["reference"], f"{_when(data['movement_date'])}  ·  {state}"], details)

    _section_title(p, "Mercadoria")
    with_vat = data["movement_type"] == "GR"
    rows = []
    for l in data["lines"]:
        rows.append([l["product_code"], l["description"], _qty(l["quantity"]) + (f" {l['unit']}" if l["unit"] else ""),
                     kz(l["unit_price"]), (f"{l['tax_code']} {l['vat_rate']:g} %" + (f" {l['exemption_code']}" if l["exemption_code"] else "")) if with_vat else "-",
                     kz(l["line_net"])])
        for lot_text in l.get("lots") or []:  # the lots the goods left in: Lote L001 · Val. 31/12/2027
            rows.append(["", "   " + lot_text, "", "", "", ""])
    _table(p, ["Código", "Descrição", "Quantidade", "Preço", "IVA", "Valor"], rows,
           [0.13, 0.33, 0.14, 0.14, 0.11, 0.15], ["l", "l", "r", "r", "l", "r"],
           total=["", "Total com IVA" if with_vat else "Total", "", "", kz(data["vat_total"]) if with_vat else "", kz(data["gross_total"])])
    if data.get("notes"):
        p.need(10 * mm)
        p.y -= 6 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8.5)
        c.drawString(MARGIN, p.y, f"Observações: {data['notes']}"[:140])
    if data["status"] == "ANULADA":
        p.need(10 * mm)
        p.y -= 6 * mm
        c.setFont("Helvetica-Bold", 9)
        c.drawString(MARGIN, p.y, f"Anulada em {_when(data['cancelled_at'])}: {data['cancel_reason']}"[:140])

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(MARGIN, MARGIN, f"{data['document_hash'][6:10] if data['document_hash'].startswith('SIMUL-') else data['document_hash'][:4]}"
                 f" - SIMUL - Processado por programa não homologado (simulação)  ·  impresso em {_when(datetime.now(LUANDA))}")
    c.showPage()
    c.save()
    return buffer.getvalue()
