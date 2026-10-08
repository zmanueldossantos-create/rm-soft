"""The movements report of a till: the lines of the journal with their payment method, the totals in and out,
the sales by method, a transfer received but not confirmed flagged as such, and the PDF produced."""
import uuid
from datetime import timedelta

import pytest
from sqlalchemy import text

from app.models.cash_movement import CashMovementType
from app.models.point_of_sale import PointOfSale
from app.models.service import Service
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_report_service import get_movements_report_data
from app.services.cash_session_service import open_session
from app.services.invoice_service import create_invoice
from app.utils.cash_report_pdf import generate_movements_report_pdf


@pytest.mark.asyncio
async def test_the_movements_report_totals_the_journal(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor, pos_id = ctx["company"].id, ctx["gestor"], ctx["pos"].id
    other_method_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-MOV", name="Servico movimentos", price=1000.0, vat_id=ctx["vat_nor"].id)
    other = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name=f"Caixa {uuid.uuid4().hex[:6]}")
    db.add_all([service, other])
    await db.commit()
    await open_session(db, company_id, other.id, gestor, opening_amount=500)
    session = await open_session(db, company_id, pos_id, gestor, opening_amount=1000)

    for method_id in (ctx["pm_numerario"].id, other_method_id):  # 1140 each
        await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA_RECIBO",
                             lines_input=[{"service_id": service.id, "quantity": 1}], amount_received=1140.0,
                             payment_method_id=method_id, cash_session_id=session.id)
    await create_cash_movement(db, company_id, CashMovementType.TRANSFERENCIA, gestor, amount=300,
                               source_pos_id=pos_id, destination_pos_id=other.id)
    await create_cash_movement(db, company_id, CashMovementType.TRANSFERENCIA, gestor, amount=200,
                               source_pos_id=other.id, destination_pos_id=pos_id)  # not yet received

    day = session.business_date
    data = await get_movements_report_data(db, company_id, pos_id, day - timedelta(days=1), day + timedelta(days=1))
    assert data["total_in"] == 2480 and data["total_out"] == 300  # 1140 + 1140 + 200 in, 300 out
    assert sorted((m["is_cash"], m["amount"]) for m in data["by_method"]) == [(False, 1140.0), (True, 1140.0)]
    assert any(e["description"].endswith("por confirmar") for e in data["entries"])
    assert generate_movements_report_pdf(data).startswith(b"%PDF")
