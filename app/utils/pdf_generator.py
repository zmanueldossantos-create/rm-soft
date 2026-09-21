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

from app.core.tax_exemptions import TAX_EXEMPTION_REASONS

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
        c.drawString(col_qty, y, f"{l['quantity']:.2f}")
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
            # Official reason of the exemption motive chosen on the article (M04 when none is recorded).
            motivo = TAX_EXEMPTION_REASONS.get(code or "M04", TAX_EXEMPTION_REASONS["M04"]) if rate == 0 else "IVA"
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


def generate_invoice_pdf_a4(invoice: dict, lines: list[dict], company: dict, customer: dict | None) -> bytes:
    """Generates an A4 invoice PDF matching the Kiami reference layout precisely."""
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    page_width, page_height = A4
    margin = 18 * mm

    logo_path = _resolve_logo_path(company)
    via_label = _via_label_text(invoice.get("print_count", 1))

    # --- Top-right via-label ---
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Oblique", 8)
    c.drawRightString(page_width - margin, page_height - 12 * mm, via_label)

    top_y = page_height - margin - 8 * mm

    # --- Logo sits alone, above both the company block AND the doc-title block, so the
    # two blocks start at the exact same Y underneath it (matches the reference: company
    # name and "Factura ...: FT2026/1" are on the same horizontal line). ---
    y = top_y
    if logo_path:
        logo_size = 20 * mm
        c.drawImage(ImageReader(logo_path), margin, y - logo_size, width=logo_size, height=logo_size, preserveAspectRatio=True, mask="auto")
        y -= logo_size + 4 * mm

    # --- Left: company block. Right: doc title + client block. Both start at "y". ---
    cy = y
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margin, cy, company["name"])
    cy -= 4.5 * mm
    c.setFont("Helvetica", 8)
    c.drawString(margin, cy, f"NIF: {company['nif']}")
    cy -= 4 * mm
    if company.get("address"):
        c.drawString(margin, cy, company["address"])
        cy -= 4 * mm
    phones = " / ".join([p for p in [company.get("phone_number"), company.get("phone_number_2")] if p])
    if phones:
        c.drawString(margin, cy, f"Tel.: {phones}")
        cy -= 4 * mm
    if company.get("email"):
        c.drawString(margin, cy, f"E-mail: {company['email']}")
        cy -= 4 * mm
    if company.get("website"):
        c.drawString(margin, cy, f"Website: {company['website']}")
        cy -= 4 * mm

    right_x = page_width - margin
    doc_title = f"{DOCUMENT_TYPE_LABELS.get(invoice['invoice_type'], invoice['invoice_type'])}: {invoice['series']}/{invoice['number']}"
    ry = y
    c.setFillColor(ACCENT)
    c.setFont("Helvetica-Bold", 12)
    c.drawRightString(right_x, ry, doc_title)
    ry -= 6 * mm
    if customer:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(right_x, ry, customer["name"][:55])
        ry -= 4.2 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawRightString(right_x, ry, f"NIF: {customer['nif']}")
        ry -= 4 * mm
        if customer.get("address"):
            c.drawRightString(right_x, ry, customer["address"][:55])
            ry -= 4 * mm
    else:
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 9)
        c.drawRightString(right_x, ry, "Consumidor Final")
        ry -= 4 * mm

    y = min(cy, ry) - 4 * mm

    # --- Info bar: ALWAYS shows all 4 fields (dash if empty), matching the reference. ---
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.line(margin, y, page_width - margin, y)
    y -= 5 * mm

    info_cells = [
        ("Data de emissao", invoice.get("business_date") or "-"),
        ("Data de vencimento", invoice.get("due_date") or "-"),
        ("Modo de pagamento", invoice.get("payment_method_name") or "-"),
        ("Condicao de pagamento", invoice.get("payment_term_name") or "-"),
    ]

    cell_width = (page_width - 2 * margin) / len(info_cells)
    for i, (label, value) in enumerate(info_cells):
        cx = margin + i * cell_width
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(cx, y, label)
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 8)
        c.drawString(cx, y - 4.5 * mm, str(value)[:24])
    y -= 9 * mm
    c.setStrokeColor(BORDER)
    c.line(margin, y, page_width - margin, y)
    y -= 8 * mm

    # --- Line table: Referencia | Designacao | Qtd | Un | Preco | Desc | Taxa(%) | Total ---
    col_ref = margin
    col_desc = margin + 22 * mm
    col_qty = margin + 90 * mm
    col_un = margin + 104 * mm
    col_price = margin + 114 * mm
    col_disc = margin + 132 * mm
    col_tax = margin + 146 * mm
    col_total = page_width - margin

    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(col_ref, y, "Referencia")
    c.drawString(col_desc, y, "Designacao")
    c.drawString(col_qty, y, "Qtd")
    c.drawString(col_un, y, "Un")
    c.drawString(col_price, y, "Preco")
    c.drawString(col_disc, y, "Desc")
    c.drawString(col_tax, y, "Taxa(%)")
    c.drawRightString(col_total, y, "Total")
    y -= 2.5 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.8)
    c.line(margin, y, page_width - margin, y)
    y -= 6 * mm

    c.setFont("Helvetica", 8)
    vat_groups = {}
    total_iliquido = 0.0
    total_discount_amount = 0.0
    for i, l in enumerate(lines):
        gross = l["quantity"] * l["unit_price"]
        line_discount_amount = gross * (l.get("discount_percent", 0) / 100)
        total_iliquido += l["line_subtotal"]
        total_discount_amount += line_discount_amount

        rate = l["vat_rate_snapshot"]
        grp = vat_groups.setdefault((rate, l.get("exemption_code") if rate == 0 else None), {"incidencia": 0.0, "montante": 0.0})
        grp["incidencia"] += l["line_subtotal"]
        grp["montante"] += l["line_subtotal"] * (rate / 100)

        c.setFillColor(TEXT_PRIMARY)
        c.drawString(col_ref, y, str(l.get("code", "-"))[:12])
        name = l["product_name_snapshot"]
        c.drawString(col_desc, y, name[:34])
        if len(name) > 34:
            c.setFont("Helvetica", 7)
            c.drawString(col_desc, y - 3.3 * mm, name[34:68])
            c.setFont("Helvetica", 8)
        c.drawString(col_qty, y, f"{l['quantity']:.2f}")
        c.drawString(col_un, y, str(l.get("unit", "-")))
        c.drawString(col_price, y, fmt(l["unit_price"]))
        c.drawString(col_disc, y, f"{line_discount_amount:.2f}" if line_discount_amount else "0,00")
        tax_label = f"{rate:.2f}"
        c.drawString(col_tax, y, tax_label + (" a)" if rate == 0 else ""))
        c.drawRightString(col_total, y, fmt(l["line_total"]))
        y -= 6 * mm if len(name) <= 34 else 9 * mm

    y -= 2 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.line(margin, y, page_width - margin, y)
    y -= 7 * mm

    if invoice.get("observations"):
        c.setFillColor(ACCENT)
        c.setFont("Helvetica-Bold", 9)
        c.drawString(margin, y, "Observacoes:")
        y -= 5 * mm
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 8)
        for para in str(invoice["observations"]).split("\n"):
            for chunk_start in range(0, len(para), 100):
                c.drawString(margin, y, para[chunk_start:chunk_start + 100])
                y -= 4.5 * mm
        y -= 3 * mm

    footer_top = max(y, margin + 66 * mm)

    fy = footer_top
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 6.5)
    c.drawString(margin, fy, "SIMUL - Processado por programa nao homologado (simulacao)")
    fy -= 5 * mm

    # --- Resumo de impostos (left) + compact totals box (right), side by side ---
    resumo_top = fy
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(margin, resumo_top, "Resumo de impostos")

    totals_box_x = page_width - margin - 62 * mm

    ry2 = resumo_top - 5 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.line(margin, ry2, totals_box_x - 4 * mm, ry2)
    ry2 -= 4 * mm
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica-Bold", 7)
    c.drawString(margin, ry2, "Imposto")
    c.drawString(margin + 16 * mm, ry2, "Taxa(%)")
    c.drawString(margin + 32 * mm, ry2, "Incidencia")
    c.drawString(margin + 62 * mm, ry2, "Motivo")
    c.drawRightString(totals_box_x - 4 * mm, ry2, "Montante (AKZ)")
    ry2 -= 4.5 * mm

    total_vat = 0.0
    for rate, code in sorted(vat_groups.keys(), key=lambda k: (k[0], k[1] or "")):
        grp = vat_groups[(rate, code)]
        total_vat += grp["montante"]
        motivo = (code or "M04") if rate == 0 else "IVA"
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica", 7.5)
        c.drawString(margin, ry2, "IVA")
        c.drawString(margin + 16 * mm, ry2, f"{rate:.2f}")
        c.drawString(margin + 32 * mm, ry2, fmt(grp["incidencia"]))
        c.drawString(margin + 62 * mm, ry2, motivo)
        c.drawRightString(totals_box_x - 4 * mm, ry2, fmt(grp["montante"]))
        ry2 -= 4.2 * mm

    # Legend: the official reason of each exemption code used, in full (the table only has room for the code).
    for legend_code in sorted({k[1] or "M04" for k in vat_groups if k[0] == 0}):
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 6.5)
        c.drawString(margin, ry2, f"{legend_code} - {TAX_EXEMPTION_REASONS.get(legend_code, '')}"[:110])
        ry2 -= 3.6 * mm

    discount_global_pct = invoice.get("discount_global_percent", 0)
    gross_before_global = total_iliquido + invoice["vat_total"]
    global_discount_amount = gross_before_global * (discount_global_pct / 100) if discount_global_pct else 0
    total_discount_all = total_discount_amount + global_discount_amount

    box_rows = [
        ("Total Iliquido", total_iliquido),
        ("Total Desconto", total_discount_all),
        ("Total Imposto", invoice["vat_total"]),
    ]
    retention_rows = 2 if invoice.get("retention_total") else 0
    ty = resumo_top - 5 * mm
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.rect(totals_box_x, ty - (len(box_rows) + 1 + retention_rows) * 4.6 * mm, page_width - margin - totals_box_x, (len(box_rows) + 1 + retention_rows) * 4.6 * mm + 4 * mm, fill=0, stroke=1)
    ty -= 1 * mm
    for label, value in box_rows:
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(totals_box_x + 2 * mm, ty, label)
        c.setFillColor(TEXT_PRIMARY)
        c.drawRightString(page_width - margin - 2 * mm, ty, fmt(value))
        ty -= 4.6 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica-Bold", 8)
    c.drawString(totals_box_x + 2 * mm, ty, "Total (AKZ)")
    c.drawRightString(page_width - margin - 2 * mm, ty, fmt(invoice["total"]))
    if retention_rows:
        ty -= 4.6 * mm
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 7.5)
        c.drawString(totals_box_x + 2 * mm, ty, "Retencao na fonte")
        c.setFillColor(TEXT_PRIMARY)
        c.drawRightString(page_width - margin - 2 * mm, ty, fmt(invoice["retention_total"]))
        ty -= 4.6 * mm
        c.setFont("Helvetica-Bold", 8)
        c.drawString(totals_box_x + 2 * mm, ty, "Liquido a pagar")
        c.drawRightString(page_width - margin - 2 * mm, ty, fmt(invoice["total"] - invoice["retention_total"]))

    y = min(ry2, ty) - 6 * mm

    if invoice.get("amount_in_words"):
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, f"Total: {invoice['amount_in_words']}")
        y -= 6 * mm

    # --- Separator before Coordenadas Bancarias ---
    c.setStrokeColor(BORDER)
    c.setLineWidth(0.6)
    c.line(margin, y, page_width - margin, y)
    y -= 6 * mm

    bank_accounts = company.get("bank_accounts") or []
    if bank_accounts:
        c.setFillColor(TEXT_PRIMARY)
        c.setFont("Helvetica-Bold", 8)
        c.drawString(margin, y, "Coordenadas Bancarias")
        y -= 4.5 * mm
        c.setFont("Helvetica", 7.5)
        for b in bank_accounts:
            c.setFillColor(TEXT_PRIMARY)
            c.drawString(margin, y, f"{b['acronym']}:")
            c.setFillColor(TEXT_MUTED)
            c.drawString(margin + 18 * mm, y, f"{b['account_number']}   IBAN: {b['iban']}")
            y -= 4 * mm

    qr_buffer = _make_qr_image(invoice["qr_code_data"])
    qr_size = 20 * mm
    qr_y = margin + 8 * mm
    c.drawImage(ImageReader(qr_buffer), page_width - margin - qr_size, qr_y, width=qr_size, height=qr_size)

    if not invoice.get("is_fiscal_doc", True):
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica-Oblique", 7.5)
        c.drawString(margin, margin, "Este documento nao serve como factura")

    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7)
    c.drawRightString(page_width - margin, margin, "Pag. 1/1")

    c.save()
    buffer.seek(0)
    return buffer.read()
