"""Point 7: the history of the resources - every use (a marcação, a table's account, a reservation), what it brought
in (documents minus credit notes) and the summary per resource, cancellations and no-shows apart."""
from datetime import datetime, timedelta

import pytest
from sqlalchemy import select

from app.models.booking import BookingStatus
from app.models.invoice_line import InvoiceLine
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services.booking_charge_service import charge_booking
from app.services.booking_service import create_booking, update_booking_status
from app.services.cash_session_service import open_session
from app.services.hotel_service import LUANDA
from app.services.invoice_service import create_credit_note
from app.services.open_account_service import add_line, close_account, open_account
from app.services.resource_history_service import get_resource_history

TODAY = datetime.now(LUANDA).replace(hour=10, minute=0, second=0, microsecond=0)


async def _setup(db, ctx):
    """A practitioner (Ana) with a 60 min massage, a table (Mesa 1) and a dinner sold on its account, an idle table."""
    company_id = ctx["company"].id
    practitioner = ResourceTypeCatalog(company_id=company_id, name="Praticante", requires_service=True)
    table_type = ResourceTypeCatalog(company_id=company_id, name="Mesa", requires_service=False)
    db.add_all([practitioner, table_type])
    await db.flush()
    ana = Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=practitioner.id, name="Ana")
    mesa = Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=table_type.id, name="Mesa 1")
    idle = Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=table_type.id, name="Mesa 2")
    massage = Service(company_id=company_id, code="SPA-MAS60", name="Massagem 60 min", price=15000, vat_id=ctx["vat_nor"].id,
                      unit_of_measure_id=ctx["unit_un"].id, resource_type_id=practitioner.id, duration_minutes=60)
    dinner = Service(company_id=company_id, code="JANTAR", name="Jantar", price=1000, vat_id=ctx["vat_nor"].id,
                     unit_of_measure_id=ctx["unit_un"].id)
    db.add_all([ana, mesa, idle, massage, dinner])
    await db.commit()
    await open_session(db, company_id, ctx["pos"].id, ctx["gestor"], 0)
    return ana, mesa, idle, massage, dinner


def _cash(ctx, amount):
    return [{"payment_method_id": ctx["pm_numerario"].id, "amount": amount}]


def _window():
    return TODAY - timedelta(hours=10), TODAY + timedelta(hours=14)


@pytest.mark.asyncio
async def test_each_use_with_its_document_and_the_summary_per_resource(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    ana, mesa, idle, massage, dinner = await _setup(db, ctx)

    paid = await create_booking(db, company_id, ana.id, ctx["gestor"].id, TODAY, TODAY + timedelta(hours=1),
                                service_id=massage.id, guest_name="Maria")
    await charge_booking(db, company_id, paid.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))
    absent = await create_booking(db, company_id, ana.id, ctx["gestor"].id, TODAY + timedelta(hours=2),
                                  TODAY + timedelta(hours=3), service_id=massage.id)
    await update_booking_status(db, company_id, absent.id, BookingStatus.NO_SHOW)

    account = await open_account(db, company_id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id,
                                 label="Mesa 1", resource_id=mesa.id)
    await add_line(db, company_id, account.id, ctx["gestor"].id, quantity=2, service_id=dinner.id)
    await close_account(db, company_id, account.id, ctx["gestor"], _cash(ctx, 2280.0))

    history = await get_resource_history(db, company_id, ctx["activity"].id, None, *_window())
    kinds = sorted((e["resource_name"], e["kind"], e["status"]) for e in history["entries"])
    assert kinds == [("Ana", "MARCACAO", "CONCLUIDA"), ("Ana", "RESERVA", "NO_SHOW"), ("Mesa 1", "CONTA", "CONCLUIDA")]
    summary = {s["resource_name"]: s for s in history["summary"]}
    assert summary["Ana"]["uses"] == 1 and summary["Ana"]["no_show"] == 1 and summary["Ana"]["revenue"] == 17100.0
    assert summary["Ana"]["occupied_minutes"] == 60
    assert summary["Mesa 1"]["uses"] == 1 and summary["Mesa 1"]["revenue"] == 2280.0
    assert summary["Mesa 2"] == {**summary["Mesa 2"], "uses": 0, "revenue": 0.0, "occupied_minutes": 0}


@pytest.mark.asyncio
async def test_a_marcacao_refunded_by_a_credit_note_brings_nothing(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    ana, _, _, massage, _ = await _setup(db, ctx)
    booking = await create_booking(db, company_id, ana.id, ctx["gestor"].id, TODAY, TODAY + timedelta(hours=1),
                                   service_id=massage.id)
    _, invoice = await charge_booking(db, company_id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))).scalar_one()
    await create_credit_note(db, company_id, ctx["activity"].id, reference_invoice_id=invoice.id, credit_note_reason="ANL",
                             credit_note_cause="Cliente desistiu", lines_input=[{"invoice_line_id": line.id, "quantity": 1}])

    history = await get_resource_history(db, company_id, None, ana.id, *_window())
    entry = history["entries"][0]
    assert entry["status"] == "CANCELADA" and entry["invoice_total"] == 17100.0 and entry["credited"] == 17100.0
    assert entry["revenue"] == 0.0
    assert history["summary"][0] == {**history["summary"][0], "uses": 0, "cancelled": 1, "revenue": 0.0}


@pytest.mark.asyncio
async def test_only_the_period_asked_for(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    ana, _, _, massage, _ = await _setup(db, ctx)
    await create_booking(db, company_id, ana.id, ctx["gestor"].id, TODAY + timedelta(days=3),
                         TODAY + timedelta(days=3, hours=1), service_id=massage.id)
    assert (await get_resource_history(db, company_id, None, ana.id, *_window()))["entries"] == []


@pytest.mark.asyncio
async def test_a_reservation_still_to_come_is_planned_not_a_use(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    ana, _, _, massage, _ = await _setup(db, ctx)
    await create_booking(db, company_id, ana.id, ctx["gestor"].id, TODAY + timedelta(hours=4),
                         TODAY + timedelta(hours=5), service_id=massage.id)
    row = (await get_resource_history(db, company_id, None, ana.id, *_window()))["summary"][0]
    assert row["uses"] == 0 and row["planned"] == 1 and row["occupied_minutes"] == 0
