"""The Caixa lists the documents of its own sessions plus the invoices still awaiting a payment - not the paid invoices of elsewhere."""
import pytest

from app.models.service import Service
from app.services.cash_session_service import open_session
from app.services.invoice_service import create_invoice, create_pro_forma, create_receipt
from app.services.pos_documents_service import list_pos_documents


@pytest.mark.asyncio
async def test_pos_documents_are_this_pos_plus_invoices_awaiting_payment(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id, pos_id, gestor = ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"]
    service = Service(company_id=company_id, code="SRV-PD", name="Servico PD", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]  # 1140

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=0)
    session_id = session.id

    async def issue(invoice_type, **extra):
        invoice = await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type=invoice_type, lines_input=lines, **extra)
        return invoice.id

    here_ft = await issue("FACTURA", cash_session_id=session_id)
    here_fr = await issue("FACTURA_RECIBO", cash_session_id=session_id)
    elsewhere_unpaid = await issue("FACTURA")  # awaiting a payment: the cashier may issue its receipt
    elsewhere_paid = await issue("FACTURA")
    await create_receipt(db, company_id, activity_id, reference_invoice_id=elsewhere_paid, amount=1140.0)  # settled: not listed
    await create_pro_forma(db, company_id, activity_id, None, lines)  # has its own list

    documents = await list_pos_documents(db, company_id, pos_id, 30)
    assert {d.id for d in documents} == {here_ft, here_fr, elsewhere_unpaid}
    assert len(await list_pos_documents(db, company_id, pos_id, 2)) == 2