"""
Invoice PDF generation - thermal 80mm ticket and A4 formats.
See specification v6/v7, section 4.1: "Impression au format Ticket 80mm
(thermique) et A4, tous deux au format legal AGT" - must include logo, QR
code, ATCUD, NIF, and VAT breakdown.

ATCUD/hash/QR are simulated (Decision 2, section 4.4) - printed documents
carry a clear "NAO HOMOLOGADO" notice until the real AGT signature is live.

Visual identity matches the app's own bordeaux design system.
"""
import io
import os
import textwrap

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.colors import HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas


ACCENT = HexColor("#8B3A3A")
ACCENT_SOFT = HexColor("#F3E7E7")
TEXT_PRIMARY = HexColor("#1A1F1D")
TEXT_MUTED = HexColor("#7A8480")
BORDER = HexColor("#D8D4CE")

DOCUMENT_TYPE_LABELS = {
    "FT": "Factura",
    "FR": "Factura/Recibo",
    "NC": "Nota de Credito",
    "ND": "Nota de Debito",
    "RC": "Recibo",
    "FP": "Factura Pro-forma",
}

BANNER_LIGHT = HexColor("#E3E3E3")
BANNER_DARK = HexColor("#AFAFAF")
TABLE_HEADER_BG = HexColor("#D0D0D0")
TABLE_ROW_ALT = HexColor("#ECECEC")
TITLE_BLACK = HexColor("#161616")

# Sentence-case version for the inline "Factura no FT2026/1" line - DOCUMENT_TYPE_LABELS
# is all-caps for the big banner title, but .title()-ing it would wrongly capitalise
# connectors like "de" ("Nota De Credito").
DOCUMENT_TYPE_LABELS_SENTENCE = {
    "FT": "Factura",
    "FR": "Factura/Recibo",
    "NC": "Nota de credito",
    "ND": "Nota de debito",
    "RC": "Recibo",
    "FP": "Factura pro-forma",
}


def fmt(value: float) -> str:
    """Formats a monetary value with a space as thousand separator, e.g. 5130.5 -> '5 130.50'."""
    return f"{value:,.2f}".replace(",", " ")


def _make_qr_image(data: str):
    qr = qrcode.QRCode(box_size=3, border=1)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#1A1F1D", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return buffer


def _resolve_logo_path(company: dict) -> str | None:
    """company['logo_path'] is a URL like /uploads/logos/{id}.png - resolve
    it to the physical file on disk, since the PDF generator runs on the
    same server and can read it directly (no HTTP round trip needed)."""
    logo_url = company.get("logo_path")
    if not logo_url:
        return None
    relative = logo_url.lstrip("/")
    if os.path.exists(relative):
        return relative
    return None


def generate_invoice_pdf_thermal(invoice: dict, lines: list[dict], company: dict, customer: dict | None) -> bytes:
    """Generates an 80mm thermal ticket - matches the Kiami reference layout: centered
    company header, left-aligned client block, doc type/number on one line, a compact
    Descricao table (Qtd/P.Un/IVA%/Total per line), totals, an "Isencao" tax summary,
    and a centered footer with the validation line, QR code and thank-you message."""
    width = 80 * mm
    logo_path = _resolve_logo_path(company)

    vat_groups = {}
    total_discount_amount = 0.0
    for l in lines:
        gross = l["quantity"] * l["unit_price"]
        line_discount_amount = gross * (l.get("discount_percent", 0) / 100)
        total_discount_amount += line_discount_amount
        rate = l["vat_rate_snapshot"]
        grp = vat_groups.setdefault((rate, l.get("exemption_code") if rate == 0 else None), {"incidencia": 0.0, "montante": 0.0})

        grp.setdefault("motivo", l.get("exemption_reason") or "")
        grp["incidencia"] += l["line_subtotal"]
        grp["montante"] += l["line_subtotal"] * (rate / 100)

    discount_global_pct = invoice.get("discount_global_percent", 0)
    gross_before_global = invoice["subtotal"] + invoice["vat_total"]
    global_discount_amount = gross_before_global * (discount_global_pct / 100) if discount_global_pct else 0
    total_discount_all = total_discount_amount + global_discount_amount

    # Rough height estimate: header block + client + doc info + one row per line (2 lines
    # tall each) + totals + isencao rows + footer/QR - generous enough to avoid clipping.
    logo_extra = 18 * mm if logo_path else 0
    # Generous overestimate on purpose - raw canvas drawing has no auto-flow, and product
    # names / "Motivo" text wrap onto extra lines unpredictably, so a tight height risks
    # clipping the QR code / footer at the bottom (see the "8 100,00" example that clipped).
    height = (150 + len(lines) * 16 + len(vat_groups) * 8) * mm + logo_extra

    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=(width, height))
    margin = 3 * mm
    center_x = width / 2
    y = height - 4 * mm

    def center(text, size=8, bold=False, color=TEXT_PRIMARY):
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawCentredString(center_x, y, text)
        y -= size * 0.42 * mm + 2.2 * mm

    def left(text, size=7.5, bold=False, color=TEXT_PRIMARY, x=None):
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(x if x is not None else margin, y, text)

    def two_col(left_text, right_text, size=7.5, bold=False, color=TEXT_PRIMARY):
        nonlocal y
        c.setFillColor(color)
        c.setFont("Helvetica-Bold" if bold else "Helvetica", size)
        c.drawString(margin, y, left_text)
        c.drawRightString(width - margin, y, right_text)
        y -= size * 0.42 * mm + 2.2 * mm

    def dashed_line():
        nonlocal y
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.setDash(1, 1.5)
        c.line(margin, y, width - margin, y)
        c.setDash()
        y -= 3 * mm

    if logo_path:
        logo_size = 13 * mm
        c.drawImage(ImageReader(logo_path), center_x - logo_size / 2, y - logo_size, width=logo_size, height=logo_size, preserveAspectRatio=True, mask="auto")
        y -= logo_size + 2 * mm

    # Company name wraps onto up to two centered lines if long.
    name = company["name"]
    if len(name) > 26:
        mid = name.rfind(" ", 0, 26) if " " in name[:26] else 26
        center(name[:mid], size=10.5, bold=True)
        center(name[mid:].strip(), size=10.5, bold=True)
    else:
        center(name, size=10.5, bold=True)
    if company.get("address"):
        center(company["address"], size=7.5, color=TEXT_MUTED)
    center(f"Contribuinte: {company['nif']}", size=7.5, color=TEXT_MUTED)
    phone = company.get("phone_number") or ""
    if phone:
        center(f"Telefone: {phone}", size=7.5, color=TEXT_MUTED)
    y -= 1.5 * mm

    # --- Client block, left-aligned ---
    if customer:
        left(f"Cliente: {customer['name']}", size=7.5)
        y -= 3.2 * mm
        if customer.get("address"):
            left(f"Morada: {customer['address']}", size=7.5)
            y -= 3.2 * mm
        left(f"NIF: {customer['nif']}", size=7.5)
        y -= 3.2 * mm
    else:
        left("Cliente: Consumidor Final", size=7.5)
        y -= 3.2 * mm
    y -= 1 * mm

    # --- Document type/number, date, attendant ---
    doc_title = DOCUMENT_TYPE_LABELS.get(invoice["invoice_type"], invoice["invoice_type"])
    doc_number = f"{invoice['series']}/{invoice['number']}"
    two_col(doc_title, doc_number, size=8, bold=True)
    two_col("Data e Hora:", invoice.get("business_date", "-"), size=7.5)
    two_col("Atendido por:", company["name"][:24], size=7.5)
    y -= 1 * mm

    # --- Line items: name on its own line, then Qtd/P.Un/IVA%/Total ---
    left("Descricao", size=7.5, bold=True)
    y -= 3.2 * mm
    col_qty = margin
    col_price = margin + 16 * mm
    col_vat = margin + 42 * mm
    col_total = width - margin
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Bold", 6.5)
    c.drawString(col_qty, y, "Qtd")
    c.drawString(col_price, y, "P.Un.")
    c.drawString(col_vat, y, "IVA%")
    c.drawRightString(col_total, y, "Total")
    y -= 3.5 * mm

    for l in lines:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 7)
        name_line = l["product_name_snapshot"]
        c.drawString(margin, y, name_line[:44])
        y -= 3.2 * mm
        c.drawString(col_qty, y, f"{l['quantity']:.2f} {l.get('unit_code') or ''}".strip())  # the unit sold: 1.00 SC, 2.00 DZ...
        c.drawString(col_price, y, fmt(l["unit_price"]))
        c.drawString(col_vat, y, f"{l['vat_rate_snapshot']:.0f}")
        c.drawRightString(col_total, y, fmt(l["line_total"]))
        y -= 3.6 * mm

    dashed_line()

    # --- Totals ---
    two_col("Total Desconto:", fmt(total_discount_all), size=7.5)
    two_col("Total a pagar :", fmt(invoice["total"]), size=8.5, bold=True)
    if invoice.get("retention_total"):
        two_col("Retencao:", fmt(invoice["retention_total"]), size=7.5)
        two_col("Liquido a pagar:", fmt(invoice["total"] - invoice["retention_total"]), size=8, bold=True)
    y -= 1 * mm

    # --- Isencao / tax summary ---
    if vat_groups:
        left("Isencao" if all(k[0] == 0 for k in vat_groups) else "Resumo de impostos", size=7.5, bold=True)
        y -= 3.2 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica-Bold", 6.5)
        c.drawString(margin, y, "Taxa")
        c.drawString(margin + 12 * mm, y, "Incidencia")
        c.drawString(margin + 38 * mm, y, "Motivo")
        y -= 3.5 * mm
        for rate, code in sorted(vat_groups.keys(), key=lambda k: (k[0], k[1] or "")):
            grp = vat_groups[(rate, code)]
            # Official reason of the exemption motive, as recorded on the line when issued.
            motivo = grp.get("motivo", "") if rate == 0 else "IVA"
            c.setFillColor(TEXT_PRIMARY)
            c.setFont("Helvetica", 6.5)
            c.drawString(margin, y, f"{rate:.2f}")
            c.drawString(margin + 12 * mm, y, fmt(grp["incidencia"]))
            wrapped = textwrap.wrap(motivo, 28) or [""]
            c.drawString(margin + 38 * mm, y, wrapped[0])
            y -= 3.2 * mm
            for extra_line in wrapped[1:]:
                c.drawString(margin + 38 * mm, y, extra_line)
                y -= 3.2 * mm

    dashed_line()

    # --- Footer: validation line, QR code, thank-you ---
    center("SIMUL - Processado por programa nao homologado", size=6, color=TEXT_MUTED)
    center("(simulacao)", size=6, color=TEXT_MUTED)
    y -= 1 * mm

    qr_buffer = _make_qr_image(invoice["qr_code_data"])
    qr_size = 16 * mm
    c.drawImage(ImageReader(qr_buffer), center_x - qr_size / 2, y - qr_size, width=qr_size, height=qr_size)
    y -= qr_size + 3 * mm

    center("Obrigado pela Preferencia", size=8, bold=True)

    c.save()
    buffer.seek(0)
    return buffer.read()


PT_ORDINALS = {
    2: "Duplicado", 3: "Triplicado", 4: "Quadruplicado", 5: "Quintuplicado",
    6: "Sextuplicado", 7: "Setuplicado", 8: "Octuplicado", 9: "Nonuplicado", 10: "Decuplicado",
}


def _via_label_text(print_count: int) -> str:
    """1st print = 'Original'; subsequent reprints = 'Na via conforme o Ordinal'
    (e.g. 2nd print -> '2a via conforme o Duplicado')."""
    if print_count <= 1:
        return "Original"
    ordinal_word = PT_ORDINALS.get(print_count, f"{print_count}a via")
    return f"{print_count}a via conforme o {ordinal_word}"


def _draw_diagonal_banner(c, page_width, page_height, title_text):
    """Light-grey diagonal band across the top with a darker accent slice,
    then the big bold document-type title sitting on top of it."""
    top = page_height
    band_h = 40 * mm
    cut_x = page_width * 0.42

    p = c.beginPath()
    p.moveTo(cut_x, top)
    p.lineTo(page_width, top)
    p.lineTo(page_width, top - band_h)
    p.lineTo(cut_x - 18 * mm, top - band_h)
    p.close()
    c.setFillColor(BANNER_LIGHT)
    c.drawPath(p, fill=1, stroke=0)

    p2 = c.beginPath()
    p2.moveTo(page_width - 45 * mm, top - band_h)
    p2.lineTo(page_width, top - band_h)
    p2.lineTo(page_width, top - band_h - 14 * mm)
    p2.close()
    c.setFillColor(BANNER_DARK)
    c.drawPath(p2, fill=1, stroke=0)

    c.setFillColor(TITLE_BLACK)
    c.setFont("Helvetica-Bold", 30)
    c.drawRightString(page_width - 14 * mm, top - 26 * mm, title_text)


def _wrap_to_width(c, text, font, size, max_width):
    """Greedy word-wrap: splits text into as many lines as needed so each
    fits max_width at the given font/size (used for the company address,
    which is often too long for a single line in the identification box)."""
    words = text.split()
    lines_out = []
    current = ""
    for w in words:
        candidate = (current + " " + w).strip()
        if c.stringWidth(candidate, font, size) <= max_width or not current:
            current = candidate
        else:
            lines_out.append(current)
            current = w
    if current:
        lines_out.append(current)
    return lines_out or [""]


def _draw_company_box(c, x, y, w, company, label="Contribuinte"):
    """Rounded-border box with the issuing company's info - matches the
    reference's left-hand identification box. The address wraps onto a
    second line instead of being cut off when it does not fit."""
    addr = company.get("address") or "-"
    phones = " / ".join([p for p in [company.get("phone_number"), company.get("phone_number_2")] if p]) or "-"

    addr_label = "Localizacao: "
    addr_label_w = c.stringWidth(addr_label, "Helvetica-Bold", 9)
    addr_wrapped = _wrap_to_width(c, addr, "Helvetica", 9, w - 8 * mm - addr_label_w)

    fixed_lines = [
        ("Contribuinte: ", company["name"]),
        ("Contacto: ", phones),
        ("NIF: ", company["nif"]),
    ]

    row_h = 5.2 * mm
    total_rows = 1 + len(addr_wrapped) + 2
    box_h = total_rows * row_h + 6 * mm
    c.setStrokeColor(TEXT_MUTED)
    c.setLineWidth(0.8)
    c.roundRect(x, y - box_h, w, box_h, 3 * mm, fill=0, stroke=1)

    ty = y - 6 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 4 * mm, ty, fixed_lines[0][0])
    lbl_w = c.stringWidth(fixed_lines[0][0], "Helvetica-Bold", 9)
    c.setFont("Helvetica", 9)
    c.drawString(x + 4 * mm + lbl_w, ty, fixed_lines[0][1][:48])
    ty -= row_h

    c.setFont("Helvetica-Bold", 9)
    c.drawString(x + 4 * mm, ty, addr_label)
    c.setFont("Helvetica", 9)
    c.drawString(x + 4 * mm + addr_label_w, ty, addr_wrapped[0])
    ty -= row_h
    for extra in addr_wrapped[1:]:
        c.drawString(x + 4 * mm + addr_label_w, ty, extra)
        ty -= row_h

    for label_part, value_part in fixed_lines[1:]:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(x + 4 * mm, ty, label_part)
        label_w = c.stringWidth(label_part, "Helvetica-Bold", 9)
        c.setFont("Helvetica", 9)
        c.drawString(x + 4 * mm + label_w, ty, value_part[:48])
        ty -= row_h
    return box_h


def _draw_party_block(c, right_x, y, name, nif, address):
    ry = y
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 9.5)
    c.drawRightString(right_x, ry, name[:55])
    ry -= 4.6 * mm
    c.setFont("Helvetica", 8.5)
    if nif:
        c.drawRightString(right_x, ry, f"No de Contribuinte: {nif}")
        ry -= 4.2 * mm
    if address:
        c.drawRightString(right_x, ry, address[:55])
        ry -= 4.2 * mm
    return y - ry


def _totais_documento_box(c, x, y, w, rows, highlight_last=True):
    """Small bordered 'Descricao | Valor' style box used for Valores em
    Kwanzas - last row shaded + bold when highlight_last."""
    row_h = 5.4 * mm
    header_h = 5.5 * mm
    box_h = header_h + len(rows) * row_h

    c.setFillColor(TABLE_HEADER_BG)
    c.rect(x, y - header_h, w, header_h, fill=1, stroke=0)
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(x + 2 * mm, y - header_h + 1.6 * mm, "Descricao")
    c.drawRightString(x + w - 2 * mm, y - header_h + 1.6 * mm, "Valor")

    ry = y - header_h
    for i, (label, value) in enumerate(rows):
        is_last = highlight_last and i == len(rows) - 1
        if is_last:
            c.setFillColor(HexColor("#D8D8D8"))
            c.rect(x, ry - row_h, w, row_h, fill=1, stroke=0)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold" if is_last else "Helvetica", 8)
        c.drawString(x + 2 * mm, ry - row_h + 1.6 * mm, label)
        c.drawRightString(x + w - 2 * mm, ry - row_h + 1.6 * mm, fmt(value) + " Kz")
        ry -= row_h

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    c.rect(x, y - box_h, w, box_h, fill=0, stroke=1)
    return box_h


def generate_factura_style_a4(invoice, lines, company, customer):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    margin = 14 * mm

    via_label = _via_label_text(invoice.get("print_count", 1))
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Oblique", 7.5)
    c.drawString(margin, page_height - 8 * mm, via_label)

    doc_title = DOCUMENT_TYPE_LABELS.get(invoice["invoice_type"], invoice["invoice_type"])
    _draw_diagonal_banner(c, page_width, page_height, doc_title)

    logo_path = _resolve_logo_path(company)
    logo_top = page_height - 12 * mm
    if logo_path:
        logo_size = 20 * mm
        c.drawImage(ImageReader(logo_path), margin, logo_top - logo_size, width=logo_size, height=logo_size, preserveAspectRatio=True, mask="auto")

    box_y = page_height - 42 * mm
    box_w = 92 * mm
    box_h = _draw_company_box(c, margin, box_y, box_w, company)

    right_x = page_width - margin
    _draw_party_block(
        c, right_x, box_y - 12 * mm,
        customer["name"] if customer else "Consumidor Final",
        customer.get("nif") if customer else None,
        customer.get("address") if customer else None,
    )

    y = box_y - box_h - 8 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 10)
    doc_title_sentence = DOCUMENT_TYPE_LABELS_SENTENCE.get(invoice["invoice_type"], doc_title)
    c.drawString(margin, y, f"{doc_title_sentence} no {invoice['series']}/{invoice['number']}")
    y -= 5 * mm
    c.setFont("Helvetica", 9)
    c.drawString(margin, y, f"Data de emissao: {invoice.get('business_date', '-')}")
    y -= 8 * mm

    col_tipo = margin
    col_cod = margin + 8 * mm
    col_desc = margin + 24 * mm
    col_qt = margin + 74 * mm
    col_preco = margin + 86 * mm
    col_desc_pct = margin + 104 * mm
    col_valor = margin + 116 * mm
    tax_block_x = margin + 134 * mm
    tax_w = 32 * mm
    col_iec = tax_block_x
    col_iva = tax_block_x + tax_w / 3
    col_iselo = tax_block_x + 2 * tax_w / 3
    col_total = page_width - margin

    header_h = 8 * mm
    c.setFillColor(TABLE_HEADER_BG)
    c.rect(margin, y - header_h, page_width - 2 * margin, header_h, fill=1, stroke=0)
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 6.8)
    hy = y - 3.2 * mm
    c.drawString(col_tipo + 1 * mm, hy, "Tipo")
    c.drawString(col_cod + 1 * mm, hy, "Codigo")
    c.drawString(col_desc + 1 * mm, hy, "Descricao")
    c.drawString(col_qt, hy, "Qt")
    c.drawString(col_preco, hy, "Preco")
    c.drawString(col_desc_pct, hy, "Desc.")
    c.drawString(col_valor, hy, "Valor")
    c.drawCentredString(tax_block_x + tax_w / 2, y - 2.4 * mm, "Impostos")
    c.drawRightString(col_total - 1 * mm, hy, "Total")
    c.setFont("Helvetica", 5.8)
    c.drawCentredString(col_iec + tax_w / 6, y - header_h + 1.2 * mm, "IEC")
    c.drawCentredString(col_iva + tax_w / 6, y - header_h + 1.2 * mm, "IVA")
    c.drawCentredString(col_iselo + tax_w / 6, y - header_h + 1.2 * mm, "Iselo")
    y -= header_h

    row_h = 6.4 * mm
    c.setFont("Helvetica", 7.5)
    vat_groups = {}
    total_iliquido = 0.0
    total_discount_amount = 0.0
    for i, l in enumerate(lines):
        if i % 2 == 1:
            c.setFillColor(TABLE_ROW_ALT)
            c.rect(margin, y - row_h, page_width - 2 * margin, row_h, fill=1, stroke=0)

        gross = l["quantity"] * l["unit_price"]
        line_discount_amount = gross * (l.get("discount_percent", 0) / 100)
        total_iliquido += l["line_subtotal"]
        total_discount_amount += line_discount_amount
        rate = l["vat_rate_snapshot"]
        grp = vat_groups.setdefault((rate, l.get("exemption_code") if rate == 0 else None), {"incidencia": 0.0, "montante": 0.0})

        grp.setdefault("motivo", l.get("exemption_reason") or "")
        grp["incidencia"] += l["line_subtotal"]
        grp["montante"] += l["line_subtotal"] * (rate / 100)

        ty = y - row_h + 2.1 * mm
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 7.5)
        c.drawString(col_tipo + 1 * mm, ty, "S" if l.get("service_line") else "P")
        c.drawString(col_cod + 1 * mm, ty, str(l.get("code", "-"))[:10])
        c.drawString(col_desc + 1 * mm, ty, l["product_name_snapshot"][:32])
        c.drawString(col_qt, ty, f"{l['quantity']:.2f} {l.get('unit_code') or ''}".strip())  # the unit sold: 1.00 SC, 2.00 DZ...
        c.drawString(col_preco, ty, fmt(l["unit_price"]))
        c.drawString(col_desc_pct, ty, f"{l.get('discount_percent', 0):.0f}%")
        c.drawString(col_valor, ty, fmt(l["line_subtotal"]))
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(col_iec + tax_w / 6, ty, fmt(l.get("iec_amount", 0)))
        exemption_code_line = l.get("exemption_code")
        iva_display = exemption_code_line if (rate == 0 and exemption_code_line) else f"{rate:.0f}%"
        c.drawCentredString(col_iva + tax_w / 6, ty, iva_display)
        c.drawCentredString(col_iselo + tax_w / 6, ty, fmt(l.get("iselo_amount", 0)))
        c.setFont("Helvetica", 7.5)
        c.drawRightString(col_total - 1 * mm, ty, fmt(l["line_total"]))
        y -= row_h

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.rect(margin, y, page_width - 2 * margin, header_h + row_h * len(lines), fill=0, stroke=1)
    y -= 6 * mm

    # Legend: the official reason of each exemption code used on a 0%-VAT line - the table only
    # has room for the code itself (e.g. "M11"), the full reason is spelled out here.
    exemption_codes = sorted({code for (rate, code) in vat_groups if rate == 0 and code})
    if exemption_codes:
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 6.5)
        for code in exemption_codes:
            c.drawString(margin, y, f"{code} - {next((g.get('motivo', '') for (r, c), g in vat_groups.items() if c == code), '')}"[:120])
            y -= 3.4 * mm
        y -= 2 * mm

    y -= 2 * mm

    retention_total = invoice.get("retention_total") or 0
    left_w = 0.52 * (page_width - 2 * margin) - 4 * mm
    right_col_x = margin + left_w + 8 * mm
    right_w = (page_width - margin) - right_col_x

    section_top = y
    if retention_total > 0:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(margin, y, "Totais retidos na fonte ou cativados pelo adquirente")
        y -= 4 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica-Oblique", 6.5)
        c.drawString(margin, y, "(valores informativos nao integrados no total do documento)")
        y -= 4.5 * mm

        rh = 5 * mm
        c.setFillColor(TABLE_HEADER_BG)
        c.rect(margin, y - rh, left_w, rh, fill=1, stroke=0)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 7)
        c.drawString(margin + 1 * mm, y - rh + 1.6 * mm, "Tipo")
        c.drawString(margin + 30 * mm, y - rh + 1.6 * mm, "Imposto")
        c.drawString(margin + 55 * mm, y - rh + 1.6 * mm, "Taxa")
        c.drawRightString(margin + left_w - 1 * mm, y - rh + 1.6 * mm, "Valor")
        y -= rh
        c.setFont("Helvetica", 7.5)
        c.drawString(margin + 1 * mm, y - rh + 1.6 * mm, "II")
        c.drawString(margin + 30 * mm, y - rh + 1.6 * mm, "Retencao na fonte")
        c.drawString(margin + 55 * mm, y - rh + 1.6 * mm, "-")
        c.drawRightString(margin + left_w - 1 * mm, y - rh + 1.6 * mm, fmt(retention_total) + " Kz")
        c.setStrokeColor(BORDER)
        c.rect(margin, y - rh, left_w, rh, fill=0, stroke=1)
        y -= rh + 2 * mm

    doc_rows = [
        ("Total iliquido", total_iliquido),
        ("Total de descontos", total_discount_amount),
        ("Total de impostos (IVA)", invoice["vat_total"]),
    ]
    ry = section_top
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(right_col_x, ry, "Totais do documento (valores em kwanzas)")
    ry -= 5 * mm
    ry -= _totais_documento_box(c, right_col_x, ry, right_w, doc_rows, highlight_last=False)

    kz_rows = [
        ("Totais sem impostos", total_iliquido),
        ("Valor de impostos", invoice["vat_total"]),
        ("Valor de descontos", total_discount_amount),
        ("Valor total a pagar", invoice["total"]),
    ]
    ry -= 4 * mm
    box_h_kz = _totais_documento_box(c, right_col_x, ry, right_w, kz_rows, highlight_last=True)
    ry -= box_h_kz

    # Net amount actually due after withholding - drawn as its own bare row (no "Kz" suffix,
    # matches the historic Resumo de impostos format) rather than folded into the boxed totals.
    if retention_total > 0:
        ry -= 2 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(right_col_x + 2 * mm, ry, "Retencao na fonte")
        c.setFillColor(TEXT_PRIMARY)
        c.drawRightString(right_col_x + right_w - 2 * mm, ry, fmt(retention_total))
        ry -= 4.6 * mm
        c.setFont("Helvetica-Bold", 8)
        c.drawString(right_col_x + 2 * mm, ry, "Liquido a pagar")
        c.drawRightString(right_col_x + right_w - 2 * mm, ry, fmt(invoice["total"] - retention_total))
        ry -= 4.6 * mm

    y = min(y, ry) - 10 * mm

    if invoice.get("amount_in_words"):
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, f"Total: {invoice['amount_in_words']}")
        y -= 6 * mm

    if invoice.get("observations"):
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, "Observacoes:")
        y -= 4.5 * mm
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 7.5)
        c.drawString(margin, y, str(invoice["observations"])[:100])
        y -= 5 * mm

    bank_accounts = company.get("bank_accounts") or []
    if bank_accounts:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, "Coordenadas Bancarias")
        y -= 4.2 * mm
        c.setFont("Helvetica", 7)
        for b in bank_accounts:
            c.setFillColor(TEXT_PRIMARY)
            c.drawString(margin, y, f"{b['acronym']}:")
            c.setFillColor(TEXT_MUTED)
            c.drawString(margin + 16 * mm, y, f"{b['account_number']}  IBAN: {b['iban']}")
            y -= 3.8 * mm

    qr_buffer = _make_qr_image(invoice["qr_code_data"])
    qr_size = 22 * mm
    c.drawImage(ImageReader(qr_buffer), page_width - margin - qr_size, margin + 6 * mm, width=qr_size, height=qr_size)

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Oblique", 6.5)
    c.drawString(margin, margin + 3 * mm, "SIMUL - Processado por programa nao homologado (simulacao)")
    if invoice.get("atcud"):
        c.drawString(margin, margin, f"ATCUD: {invoice['atcud']}")

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawRightString(page_width - margin, margin, "Pag. 1/1")

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_recibo_style_a4(invoice, company, customer):
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    margin = 14 * mm

    via_label = _via_label_text(invoice.get("print_count", 1))
    top = page_height - 14 * mm
    c.setFillColor(TITLE_BLACK)
    c.setFont("Helvetica-Bold", 30)
    c.drawString(margin, top, "RECIBO")
    ty = top - 7 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 9.5)
    c.drawString(margin, ty, f"Data de emissao: {invoice.get('business_date', '-')}")

    logo_path = _resolve_logo_path(company)
    if logo_path:
        logo_size = 18 * mm
        c.drawImage(ImageReader(logo_path), page_width - margin - logo_size, top - 12 * mm, width=logo_size, height=logo_size, preserveAspectRatio=True, mask="auto")

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Oblique", 7)
    c.drawRightString(page_width - margin, top - 18 * mm, via_label)

    y = ty - 10 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 8.5)
    c.drawString(margin, y, company["name"])
    y -= 4 * mm
    c.drawString(margin, y, f"No de Contribuinte: {company['nif']}")
    y -= 4 * mm
    addr_line = company.get("address") or ""
    phones = " / ".join([p for p in [company.get("phone_number"), company.get("phone_number_2")] if p])
    tail = (" - Tel: " + phones) if phones else ""
    c.drawString(margin, y, f"{addr_line}{tail}"[:100])
    y -= 8 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(margin, y, "Contribuinte: ")
    lbl_w = c.stringWidth("Contribuinte: ", "Helvetica-Bold", 9)
    c.setFont("Helvetica", 9)
    c.drawString(margin + lbl_w, y, (customer["name"] if customer else "Consumidor Final")[:50])
    cust_y = y
    y -= 4.4 * mm
    if customer and customer.get("address"):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, "Localizacao: ")
        lbl_w2 = c.stringWidth("Localizacao: ", "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(margin + lbl_w2, y, customer["address"][:60])
        y -= 4.2 * mm
    if customer and customer.get("nif"):
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, "NIF: ")
        lbl_w3 = c.stringWidth("NIF: ", "Helvetica-Bold", 8)
        c.setFont("Helvetica", 8)
        c.drawString(margin + lbl_w3, y, customer["nif"])
        y -= 4.2 * mm

    right_x = page_width - margin
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(right_x, cust_y, "Documento de Cobranca")
    c.setFont("Helvetica", 8)
    c.drawRightString(right_x, cust_y - 4.2 * mm, f"Data emissao: {invoice.get('business_date', '-')}")

    y -= 6 * mm

    ref = invoice.get("reference_invoice")
    col_num = margin
    col_tipo = margin + 42 * mm
    col_semimp = margin + 68 * mm
    tax_block_x = margin + 100 * mm
    tax_w = 32 * mm
    col_desc = tax_block_x + tax_w + 2 * mm
    col_total = page_width - margin

    header_h = 9 * mm
    c.setFillColor(TABLE_HEADER_BG)
    c.rect(margin, y - header_h, page_width - 2 * margin, header_h, fill=1, stroke=0)
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 6.5)
    hy = y - 3.2 * mm
    c.drawString(col_num + 1 * mm, hy, "No Factura ou documento")
    c.drawString(col_tipo + 1 * mm, hy, "Tipo de documento")
    c.drawString(col_semimp + 1 * mm, hy, "Total sem imposto")
    c.drawCentredString(tax_block_x + tax_w / 2, y - 2.4 * mm, "Valor de imposto")
    c.drawString(col_desc + 1 * mm, hy, "Descontos")
    c.drawRightString(col_total - 1 * mm, hy, "Total")
    c.setFont("Helvetica", 5.6)
    c.drawCentredString(tax_block_x + tax_w / 6, y - header_h + 1.2 * mm, "IEC")
    c.drawCentredString(tax_block_x + tax_w / 2, y - header_h + 1.2 * mm, "IVA")
    c.drawCentredString(tax_block_x + 5 * tax_w / 6, y - header_h + 1.2 * mm, "IS")
    y -= header_h

    row_h = 6 * mm
    total_rows = 9
    if ref:
        ty = y - row_h + 2.1 * mm
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 7.5)
        c.drawString(col_num + 1 * mm, ty, f"{ref['invoice_type']} {ref['series']}/{ref['number']}")
        c.drawString(col_tipo + 1 * mm, ty, ref['invoice_type'])
        c.drawString(col_semimp + 1 * mm, ty, fmt(ref["subtotal"]))
        c.setFont("Helvetica", 6.8)
        c.drawCentredString(tax_block_x + tax_w / 6, ty, "0,00")
        c.drawCentredString(tax_block_x + tax_w / 2, ty, fmt(ref["vat_total"]))
        c.drawCentredString(tax_block_x + 5 * tax_w / 6, ty, "0,00")
        c.setFont("Helvetica", 7.5)
        c.drawRightString(col_total - 1 * mm, ty, fmt(invoice["total"]))
        y -= row_h

    for _ in range(total_rows - (1 if ref else 0)):
        y -= row_h

    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.rect(margin, y, page_width - 2 * margin, header_h + row_h * total_rows, fill=0, stroke=1)
    y -= 10 * mm

    left_w = 0.5 * (page_width - 2 * margin) - 4 * mm
    right_col_x = margin + left_w + 8 * mm
    right_w = (page_width - margin) - right_col_x

    section_top = y
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(margin, y, "Valores totais")
    y -= 5 * mm
    curr_rows = [("Divisas", "-"), ("Taxa de Cambios", "-"), ("Valor em divisas", "-")]
    rh = 5 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.5)
    for label, value in curr_rows:
        c.rect(margin, y - rh, left_w, rh, fill=0, stroke=1)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(margin + 2 * mm, y - rh + 1.6 * mm, label)
        c.setFillColor(TEXT_PRIMARY)
        c.drawRightString(margin + left_w - 2 * mm, y - rh + 1.6 * mm, value)
        y -= rh

    kz_rows = [
        ("Totais sem impostos", invoice["subtotal"]),
        ("Valor de impostos", invoice["vat_total"]),
        ("Valor de descontos", 0.0),
        ("Valor total a pagar", invoice["total"]),
    ]
    ry = section_top
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawRightString(right_col_x + right_w, ry, "Valores em Kwanzas")
    ry -= 5 * mm
    ry -= _totais_documento_box(c, right_col_x, ry, right_w, kz_rows, highlight_last=True)

    y = min(y, ry) - 10 * mm

    qr_buffer = _make_qr_image(invoice["qr_code_data"])
    qr_size = 26 * mm
    qr_x = page_width / 2 - qr_size / 2
    c.drawImage(ImageReader(qr_buffer), qr_x, y - qr_size, width=qr_size, height=qr_size)
    y -= qr_size + 10 * mm

    banner_text = "SIMUL - DOCUMENTO PROCESSADO POR PROGRAMA NAO HOMOLOGADO"
    banner_h = 10 * mm
    banner_w = page_width - 2 * margin
    banner_x = margin
    c.setStrokeColor(TEXT_PRIMARY)
    c.setLineWidth(1.2)
    c.rect(banner_x, y - banner_h, banner_w, banner_h, fill=0, stroke=1)
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 10)
    c.drawCentredString(page_width / 2, y - banner_h / 2 - 1.5 * mm, banner_text)

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawString(margin, margin, "Pag. 1/1")

    c.save()
    buffer.seek(0)
    return buffer.read()


def generate_invoice_pdf_a4(invoice: dict, lines: list[dict], company: dict, customer: dict | None) -> bytes:
    """Dispatches to the RECIBO-style template (RC has no product/service lines of its own -
    see create_receipt docstring, it references the settled invoice instead) or the FACTURA-style
    template used by every other document type (FT, FR, FP, NC, ND)."""
    if invoice["invoice_type"] == "RC":
        return generate_recibo_style_a4(invoice, company, customer)
    return generate_factura_style_a4(invoice, lines, company, customer)