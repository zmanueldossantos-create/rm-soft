"""The drawer journal lists the money that actually entered: one line per payment - a Fatura billed later or a credit note has none."""
from datetime import date

import pytest
from sqlalchemy import select, text

from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.daily_report_service import get_daily_report
from app.services.invoice_service import create_credit_note, create_invoice, create_receipt


@pytest.mark.asyncio
async def test_journal_lists_the_payments_not_the_documents(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    multicaixa_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-JP", name="Servico JP", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]  # 1140

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    session_id = session.id
    ft = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines, cash_session_id=session_id)
    ft_id = ft.id
    line_id = (await db.execute(select(InvoiceLine.id).where(InvoiceLine.invoice_id == ft_id))).scalar_one()
    await create_receipt(db, company_id, activity_id, reference_invoice_id=ft_id, amount=500.0, cash_session_id=session_id)
    await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA_RECIBO", lines_input=lines,
                         cash_session_id=session_id, payment_method_id=multicaixa_id)
    await create_credit_note(db, company_id, activity_id, reference_invoice_id=ft_id, credit_note_reason="RTF",
                             credit_note_cause="Teste", lines_input=[{"invoice_line_id": line_id, "quantity": 1}])

    entries = await get_daily_report(db, company_id, pos_id, date.today(), date.today())
    sales = [e for e in entries if e["type"] == "venda"]
    assert sorted((e["description"].split(" ")[0], e["amount"]) for e in sales) == [("FR", 1140.0), ("RC", 500.0)]
    assert all(e["direction"] == "entrada" for e in sales)  # no line for the FT billed later nor for the credit note