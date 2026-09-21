"""
The exemption code of a 0% article is copied onto every line issued: invoice, debit note, pro-forma - and a credit
note copies it from the line it credits. A taxed line, and a motive that is not official (the catalog's "NA"),
leave it empty.
"""
from datetime import date

import pytest
from sqlalchemy import select

from app.models.country import Country
from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.models.vat_code import VatCode
from app.services.invoice_service import create_credit_note, create_debit_note, create_invoice, create_pro_forma


async def _codes(db, document_id):
    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == document_id))).scalars().all()
    return {l.service_id: l.exemption_code for l in lines}


@pytest.mark.asyncio
async def test_exemption_code_is_copied_on_every_document(db, company_with_essentials):
    ctx = company_with_essentials
    country = Country(code="AO", name="Angola")
    db.add(country)
    await db.flush()
    m11 = VatCode(code="M11", name="Isento teste", rate=0, country_id=country.id, valid_from=date(2021, 1, 1))
    na = VatCode(code="NA", name="Nao aplicavel", rate=0, country_id=country.id, valid_from=date(2021, 1, 1))
    db.add_all([m11, na])
    await db.flush()
    exempt = Service(company_id=ctx["company"].id, code="SRV-EX", name="Servico isento", price=1000.0,
                     vat_id=ctx["vat_ise"].id, exemption_reason_id=m11.id)
    invalid = Service(company_id=ctx["company"].id, code="SRV-NA", name="Servico NA", price=1000.0,
                      vat_id=ctx["vat_ise"].id, exemption_reason_id=na.id)
    taxed = Service(company_id=ctx["company"].id, code="SRV-TX", name="Servico taxado", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add_all([exempt, invalid, taxed])
    await db.commit()
    exempt_id, invalid_id, taxed_id = exempt.id, invalid.id, taxed.id

    invoice = await create_invoice(
        db, ctx["company"].id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": s, "quantity": 1} for s in (exempt_id, invalid_id, taxed_id)],
    )
    invoice_id = invoice.id
    assert await _codes(db, invoice_id) == {exempt_id: "M11", invalid_id: None, taxed_id: None}

    lines = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().all()
    line_ids = [l.id for l in lines]
    credit_note = await create_credit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id,
        # RTF, not ANL: a full ANL credit note annuls the invoice, and a debit note on an annulled invoice is refused.
        credit_note_reason="RTF", credit_note_cause="Rectificacao de teste",
        lines_input=[{"invoice_line_id": i, "quantity": 1} for i in line_ids],
    )
    credit_note_id = credit_note.id
    assert await _codes(db, credit_note_id) == {exempt_id: "M11", invalid_id: None, taxed_id: None}

    debit_note = await create_debit_note(
        db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice_id, customer_id=None,
        lines_input=[{"service_id": exempt_id, "quantity": 1}],
    )
    debit_note_id = debit_note.id
    assert await _codes(db, debit_note_id) == {exempt_id: "M11"}

    pro_forma = await create_pro_forma(
        db, ctx["company"].id, ctx["activity"].id, None, [{"service_id": exempt_id, "quantity": 1}],
    )
    pro_forma_id = pro_forma.id
    assert await _codes(db, pro_forma_id) == {exempt_id: "M11"}