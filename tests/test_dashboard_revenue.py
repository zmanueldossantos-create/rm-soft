"""
The dashboard counts sales only: a pro-forma is a quote and a receipt settles an invoice already counted, so both
stay out; a credit note is subtracted. Pro-formas are also left out of the submission-status breakdown.
"""
import pytest
from sqlalchemy import select

from app.models.invoice_line import InvoiceLine
from app.models.service import Service
from app.services.dashboard_service import get_dashboard_summary
from app.services.invoice_service import create_credit_note, create_invoice, create_pro_forma, create_receipt


@pytest.mark.asyncio
async def test_dashboard_counts_sales_only_and_subtracts_credit_notes(db, company_with_essentials, mark_electronic):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-DB", name="Serviço dashboard", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id

    invoice = await create_invoice(  # 2 x 1140 = 2280
        db, company_id, activity_id, customer_id=None, invoice_type="FACTURA",
        lines_input=[{"service_id": service_id, "quantity": 2}],
    )
    invoice_id = invoice.id
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice_id))).scalars().one()
    line_id = line.id
    await create_credit_note(  # - 1140
        db, company_id, activity_id, reference_invoice_id=invoice_id, credit_note_reason="RTF",
        credit_note_cause="Devolução de uma unidade", lines_input=[{"invoice_line_id": line_id, "quantity": 1}],
    )
    await create_pro_forma(db, company_id, activity_id, None, [{"service_id": service_id, "quantity": 1}])  # a quote
    await create_receipt(db, company_id, activity_id, reference_invoice_id=invoice_id, amount=500.0)  # already counted
    summary = await get_dashboard_summary(db, company_id)
    assert not summary["agt_realtime"] and sum(summary["invoices_by_status"].values()) == 0  # MANUAL: no AGT states
    await mark_electronic(company_id)

    summary = await get_dashboard_summary(db, company_id)
    assert summary["revenue_today"] == 1140.0 and summary["revenue_month"] == 1140.0
    assert summary["invoice_count_month"] == 2  # the invoice and the credit note
    assert summary["invoices_by_status"]["PENDENTE"] == 3  # invoice, credit note, receipt - not the pro-forma


@pytest.mark.asyncio
async def test_the_painel_blocks_follow_the_permissions(db, company_with_essentials):
    """The Painel's extra blocks: the 30 days, the best sellers, the money owed - and none for who may not see it;
    the last documents are sales only (never the pro-forma)."""
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-PN", name="Serviço painel", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    service_id = service.id
    await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA",
                         lines_input=[{"service_id": service_id, "quantity": 3}])  # 3 420, not paid yet
    await create_pro_forma(db, company_id, activity_id, None, [{"service_id": service_id, "quantity": 1}])

    summary = await get_dashboard_summary(db, company_id, {"invoices:view"})
    assert len(summary["sales_30_days"]) == 30 and summary["sales_30_days"][-1]["total"] == 3420.0
    assert summary["top_products_today"][0]["name"] == "Serviço painel" and summary["top_products_today"][0]["quantity"] == 3
    assert summary["receivables"]["total"] == 3420.0 and summary["receivables"]["count"] == 1
    assert all(i["invoice_type"] != "PRO_FORMA" for i in summary["recent_invoices"])
    assert "payables" not in summary and "tills" not in summary  # no permission for those blocks
    assert summary["low_stock_products"] == []  # nor for the stock

    every = {"invoices:view", "purchases:view", "tesouraria:overview", "stock:view", "production:view"}
    summary = await get_dashboard_summary(db, company_id, every)  # the gestor: every block, even when empty
    assert summary["payables"]["total"] == 0 and summary["tills"] == [] and summary["production_today"]["count"] == 0
    assert summary["expiring"]["lots"] == []
