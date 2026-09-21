"""The dashboard follows the catalog rules: revenue_sign decides what counts as a sale, sent_to_agt what has a submission status."""
import pytest
from sqlalchemy import text

from app.models.service import Service
from app.services.dashboard_service import get_dashboard_summary
from app.services.invoice_service import create_invoice, create_pro_forma


async def _set_rule(db, code, **values):
    sets = ", ".join(f"{key} = :{key}" for key in values)
    await db.execute(text(f"UPDATE document_types SET {sets} WHERE code = :code"), {**values, "code": code})
    await db.commit()


@pytest.mark.asyncio
async def test_dashboard_follows_the_revenue_sign_and_sent_to_agt_rules(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, activity_id = ctx["company"].id, ctx["activity"].id
    service = Service(company_id=company_id, code="SRV-DR", name="Servico DR", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()
    await db.refresh(service)
    lines = [{"service_id": service.id, "quantity": 1}]  # 1140

    await create_invoice(db, company_id, activity_id, customer_id=None, invoice_type="FACTURA", lines_input=lines)
    await create_pro_forma(db, company_id, activity_id, None, lines)

    summary = await get_dashboard_summary(db, company_id)
    assert summary["revenue_month"] == 1140.0 and summary["invoice_count_month"] == 1
    assert summary["invoices_by_status"]["PENDENTE"] == 1  # the pro-forma is not sent to the AGT

    try:
        await _set_rule(db, "FP", revenue_sign=1, sent_to_agt=True)
        summary = await get_dashboard_summary(db, company_id)
        assert summary["revenue_month"] == 2280.0 and summary["invoice_count_month"] == 2
        assert summary["invoices_by_status"]["PENDENTE"] == 2
    finally:
        await _set_rule(db, "FP", revenue_sign=0, sent_to_agt=False)