"""The closing report of a till session: built only for a closed session, its figures match the closing, a reprint
after later movements is identical, and the PDF is produced."""
import uuid

import pytest
from sqlalchemy import text

from app.models.cash_movement import CashMovementType
from app.models.point_of_sale import PointOfSale
from app.models.service import Service
from app.services.cash_movement_service import create_cash_movement
from app.services.cash_report_service import SessionNotClosedError, get_closing_report_data
from app.services.cash_session_service import close_session, open_session
from app.services.invoice_service import create_invoice
from app.utils.cash_report_pdf import generate_closing_report_pdf


@pytest.mark.asyncio
async def test_the_closing_report_matches_the_closing_and_never_moves(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, gestor, pos_id = ctx["company"].id, ctx["gestor"], ctx["pos"].id
    multicaixa_id = (await db.execute(text("SELECT id FROM payment_method_catalog WHERE code = 'MB'"))).scalar_one()
    service = Service(company_id=company_id, code="SRV-REP", name="Servico relatorio", price=1000.0, vat_id=ctx["vat_nor"].id)
    db.add(service)
    await db.commit()

    session = await open_session(db, company_id, pos_id, gestor, opening_amount=1000)
    with pytest.raises(SessionNotClosedError):
        await get_closing_report_data(db, company_id, session.id)
    for method_id in (ctx["pm_numerario"].id, multicaixa_id):  # 1140 each
        await create_invoice(db, company_id, ctx["activity"].id, customer_id=None, invoice_type="FACTURA_RECIBO",
                             lines_input=[{"service_id": service.id, "quantity": 1}], amount_received=1140.0,
                             payment_method_id=method_id, cash_session_id=session.id)
    await close_session(db, company_id, session.id, gestor.id, closing_amount_counted=2100, closing_notes="Troco")

    data = await get_closing_report_data(db, company_id, session.id)
    assert data["summary"]["expected_cash"] == 2140 and data["counted"] == 2100 and data["difference"] == -40
    assert data["summary"]["total_received"] == 2280 and data["notes"] == "Troco"
    assert [(d["type"], d["count"], d["total"]) for d in data["documents"]] == [("FACTURA_RECIBO", 2, 2280.0)]
    assert generate_closing_report_pdf(data).startswith(b"%PDF")

    # the next day: the till reopens and sends money away - the old report does not move
    other = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name=f"Caixa {uuid.uuid4().hex[:6]}")
    db.add(other)
    await db.commit()
    await open_session(db, company_id, other.id, gestor, opening_amount=0)
    await open_session(db, company_id, pos_id, gestor, opening_amount=2100)
    await create_cash_movement(db, company_id, CashMovementType.TRANSFERENCIA, gestor, amount=500,
                               source_pos_id=pos_id, destination_pos_id=other.id)
    again = await get_closing_report_data(db, company_id, session.id)
    assert again["summary"]["transfers_out"] == 0 and again["summary"]["expected_cash"] == 2140
