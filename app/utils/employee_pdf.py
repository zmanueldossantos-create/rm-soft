"""
The employee's file in A4 (Recursos Humanos): identification with the photo, professional data, pay, qualifications
and the documents handed in. Internal document, same identity as the cash reports.
"""
import io
from datetime import date, datetime

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from app.models.employee import GENDERS, ID_DOCUMENT_TYPES, MARITAL_STATUSES, PAYMENT_METHODS
from app.utils.cash_report_pdf import CONTENT_W, LUANDA, MARGIN, _fit, _Page, _draw_header, _section_title, _table, _when, kz
from app.utils.pdf_generator import TEXT_MUTED, TEXT_PRIMARY

PHOTO_W, PHOTO_H = 30 * mm, 38 * mm


def _day(value) -> str:
    if not value:
        return "-"
    if isinstance(value, str):
        value = date.fromisoformat(value[:10])
    return value.strftime("%d/%m/%Y")


def _fields(p: _Page, pairs: list[tuple[str, str]], width: float = CONTENT_W, columns: int = 3) -> None:
    """Label / value pairs on columns, row after row; an empty value shows «-»."""
    c = p.c
    col_w = width / columns
    for start in range(0, len(pairs), columns):
        p.need(9 * mm)
        for k, (label, value) in enumerate(pairs[start:start + columns]):
            x = MARGIN + k * col_w
            c.setFillColor(TEXT_MUTED)
            c.setFont("Helvetica", 7.5)
            c.drawString(x, p.y, label.upper())
            c.setFillColor(TEXT_PRIMARY)
            c.setFont("Helvetica", 9.5)
            c.drawString(x, p.y - 4 * mm, _fit(c, str(value or "-"), "Helvetica", 9.5, col_w - 4 * mm))
        p.y -= 8.5 * mm


def _section(p: _Page, title: str) -> None:
    """A section title, a little apart from the block above."""
    p.y -= 2 * mm
    _section_title(p, title)


def _paragraph(p: _Page, label: str, text: str | None) -> None:
    if not text:
        return
    c = p.c
    p.need(10 * mm)
    c.setFillColor(TEXT_MUTED)
    c.setFont("Helvetica", 7.5)
    c.drawString(MARGIN, p.y, label.upper())
    p.y -= 4.2 * mm
    c.setFillColor(TEXT_PRIMARY)
    c.setFont("Helvetica", 9.5)
    for raw in text.splitlines() or [""]:
        line = raw
        while line:
            cut = len(line)
            while cut and c.stringWidth(line[:cut], "Helvetica", 9.5) > CONTENT_W:
                cut = line.rfind(" ", 0, cut) if " " in line[:cut] else cut - 1
            p.need(5 * mm)
            c.drawString(MARGIN, p.y, line[:cut])
            p.y -= 4.5 * mm
            line = line[cut:].lstrip()
    p.y -= 3 * mm


def generate_employee_pdf(e: dict, documents: dict, photo: bytes | None, company: dict) -> bytes:
    buffer = io.BytesIO()
    c = canvas.Canvas(buffer, pagesize=A4)
    c.setTitle(f"Ficha do colaborador {e['number']} - {e['full_name']}")
    p = _Page(c)
    state = "Ativo" if e["is_active"] else f"Saiu em {_day(e['left_on'])}"
    _draw_header(p, company, "FICHA DO COLABORADOR", [e["full_name"], f"Matrícula {e['number']}"],
                 [("Admissão", _day(e["hired_on"])), ("Estado", state), ("Impresso em", _when(datetime.now(LUANDA)))])

    _section(p, "Identificação")
    top = p.y
    if photo:
        try:
            c.drawImage(ImageReader(io.BytesIO(photo)), MARGIN + CONTENT_W - PHOTO_W, top - PHOTO_H + 3 * mm, PHOTO_W, PHOTO_H,
                        preserveAspectRatio=True, anchor="c", mask="auto")
        except Exception:  # an unreadable image never stops the file
            pass
    document = ID_DOCUMENT_TYPES.get(e.get("id_document_type") or "", "Documento")
    width = CONTENT_W - (PHOTO_W + 4 * mm if photo else 0)
    _fields(p, [("Nome completo", e["full_name"])], width=width, columns=1)
    _fields(p, [
        ("Género", GENDERS.get(e.get("gender") or "")),
        ("Data de nascimento", _day(e.get("birth_date"))), ("Estado civil", MARITAL_STATUSES.get(e.get("marital_status") or "")),
        ("Nacionalidade", e.get("nationality")), ("NIF", e.get("nif")),
        (document, e.get("id_document_number")), ("Válido até", _day(e.get("id_expires_on"))),
        ("N.º de segurança social", e.get("social_security_number")), ("Telefone", e.get("phone")),
    ], width=width)
    p.y = min(p.y, top - PHOTO_H - 2 * mm) if photo else p.y
    _fields(p, [("Nome do pai", e.get("father_name")), ("Nome da mãe", e.get("mother_name")), ("Email", e.get("email"))])
    _paragraph(p, "Morada", e.get("address"))

    _section(p, "Dados profissionais")
    _fields(p, [
        ("Departamento", e.get("department")), ("Categoria profissional", e.get("category")),
        ("Função / cargo", e.get("job_title")), ("Local de trabalho", e.get("establishment")),
        ("Data de admissão", _day(e.get("hired_on"))), ("Tipo de contrato", e.get("contract_type")),
        ("Fim do contrato", _day(e.get("contract_ends_on"))), ("Fim do período experimental", _day(e.get("probation_ends_on"))),
        ("Horário de trabalho", e.get("work_schedule")), ("Conta de utilizador", e.get("user_name")),
    ])
    if not e["is_active"]:
        _fields(p, [("Data de saída", _day(e.get("left_on"))), ("Motivo da saída", e.get("leaving_reason_label"))])
        _paragraph(p, "Observação da saída", e.get("leaving_note"))

    _section(p, "Remuneração")
    _fields(p, [("Salário base mensal", kz(e["base_salary"])),
                ("Forma de pagamento", PAYMENT_METHODS.get(e.get("payment_method") or "")),
                ("Banco", e.get("bank")), ("IBAN", " ".join((e.get("iban") or "")[i:i + 4] for i in range(0, len(e.get("iban") or ""), 4)))])

    _section(p, "Habilitações")
    _fields(p, [("Nível de escolaridade", e.get("education_level"))], columns=1)
    _paragraph(p, "Formação profissional", e.get("training"))
    _paragraph(p, "Experiência anterior", e.get("experience"))
    _paragraph(p, "Observações", e.get("notes"))

    _section(p, "Documentos do processo")
    rows = [[_fit(c, d["name"] or "-", "Helvetica", 9, 0.42 * CONTENT_W), _day(d["delivered_on"]),
             _day(d["expires_on"]) + (" (expirado)" if d.get("expired") else ""), "Sim" if d["has_file"] else "Papel"]
            for d in documents["documents"]]
    _table(p, ["Documento", "Entregue em", "Válido até", "Digitalizado"], rows, [0.45, 0.18, 0.22, 0.15], ["l", "l", "l", "l"])
    missing = [item["name"] for item in documents["checklist"] if not item["delivered"]]
    if missing:
        _paragraph(p, "Em falta", ", ".join(missing))

    # the signatures
    p.need(16 * mm, floor=10 * mm)
    p.y -= 10 * mm
    c.setStrokeColor(TEXT_MUTED)
    c.setLineWidth(0.5)
    half = CONTENT_W / 2
    for k, label in enumerate(("O colaborador", "Pela empresa")):
        x = MARGIN + k * half + 10 * mm
        c.line(x, p.y, x + half - 20 * mm, p.y)
        c.setFillColor(TEXT_MUTED)
        c.setFont("Helvetica", 8)
        c.drawCentredString(x + (half - 20 * mm) / 2, p.y - 4 * mm, label)
    c.showPage()
    c.save()
    return buffer.getvalue()
