"""Modo formação: the documents take their own series (FR2026F), mode FORMACAO, are never sent to the AGT (validated
at once by the simulation in Faturação Eletrónica), stay out of the SAF-T and the VAT, and print a watermark; leaving
the mode, the real numbering goes on where it stood."""
import io
from datetime import date

import pytest
from sqlalchemy import select

from app.models.company import Company
from app.models.invoice import InvoiceStatus
from app.models.service import Service
from app.services.agt_queue import queue_for_agt
from app.services.invoice_service import create_invoice
from app.services.saf_t_export_service import export_saf_t_for_period
from app.services.vat_return_service import _sales_lines
from app.utils.pdf_generator import generate_factura_style_a4, generate_invoice_pdf_thermal

YEAR = date.today().year


async def _issue(db, ctx, service):
    return await create_invoice(db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
                                lines_input=[{"service_id": service.id, "quantity": 1}])


async def _service(db, ctx):
    service = Service(company_id=ctx["company"].id, code="SRV-T", name="Aula", vat_id=ctx["vat_nor"].id, price=1000.0)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    return service


@pytest.mark.asyncio
async def test_training_documents_have_their_own_series_and_no_fiscal_value(db, company_with_essentials):
    ctx = company_with_essentials
    service = await _service(db, ctx)
    company = await db.get(Company, ctx["company"].id)
    company.training_mode = True
    await db.commit()

    first = await _issue(db, ctx, service)
    assert (first.issuance_mode, first.series, first.number) == ("FORMACAO", f"FT{YEAR}F", 1)
    second = await _issue(db, ctx, service)
    assert (second.series, second.number) == (f"FT{YEAR}F", 2)

    company.training_mode = False
    await db.commit()
    real = await _issue(db, ctx, service)
    assert real.issuance_mode == "MANUAL" and real.series != f"FT{YEAR}F" and real.number == 1  # its own numbering

    start, end = date(YEAR, date.today().month, 1), date.today()
    declared = {inv.id for inv, *_ in await _sales_lines(db, company.id, start, end)}
    assert real.id in declared and first.id not in declared and second.id not in declared
    xml = (await export_saf_t_for_period(db, company.id, YEAR, date.today().month)).decode()
    assert f"FT{YEAR}F" not in xml and f"/{real.number}" in xml


@pytest.mark.asyncio
async def test_in_faturacao_eletronica_the_simulation_validates_it(db, company_with_essentials):
    ctx = company_with_essentials
    service = await _service(db, ctx)
    company = await db.get(Company, ctx["company"].id)
    company.training_mode, company.issuance_mode = True, "ELETRONICA"
    await db.commit()
    invoice = await _issue(db, ctx, service)
    await queue_for_agt(db, invoice)
    assert invoice.status == InvoiceStatus.VALIDADA and invoice.agt_next_attempt_at is None  # never sent


def test_the_watermark():
    pypdf = pytest.importorskip("pypdf")
    line = {"quantity": 1.0, "unit_price": 1000.0, "discount_percent": 0, "line_subtotal": 1000.0, "vat_rate_snapshot": 14.0,
            "exemption_code": None, "exemption_reason": None, "service_line": True, "code": "SRV", "product_name_snapshot": "Aula",
            "unit_code": "UN", "iec_amount": 0, "iselo_amount": 0, "line_total": 1140.0}
    company = {"name": "Escola Teste", "nif": "5000999001", "address": "Rua X", "phone_number": "+244923000000",
               "logo_path": None, "bank_accounts": []}
    invoice = {"invoice_type": "FT", "series": f"FT{YEAR}F", "number": 1, "business_date": f"{YEAR}-10-30", "print_count": 1,
               "retention_total": 0, "subtotal": 1000.0, "vat_total": 140.0, "total": 1140.0, "discount_global_percent": 0,
               "amount_in_words": None, "observations": None, "qr_code_data": "x", "payments": [], "payment_method_name": None,
               "training": True}
    for pdf in (generate_factura_style_a4(invoice, [line], company, None),
                generate_invoice_pdf_thermal(invoice, [line], company, None)):
        text = "".join(p.extract_text() for p in pypdf.PdfReader(io.BytesIO(pdf)).pages)
        assert "SEM VALOR FISCAL" in text and "FORMAÇÃO / DEMONSTRAÇÃO" in text
