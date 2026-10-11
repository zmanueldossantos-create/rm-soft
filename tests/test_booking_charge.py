"""Spa / Salão / Consultório (point 3): Cobrar uma marcação - the booked service sold at the till, the booking
concluded with its invoice and still holding its slot; no manual Concluída for a priced marcação."""
from datetime import datetime, timedelta

import pytest

from app.models.booking import BookingStatus
from app.models.invoice import Invoice
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services.booking_charge_service import BookingNotChargeableError, charge_booking
from app.services.booking_service import (
    BookingNotEditableError, BookingOverlapError, create_booking, update_booking_status,
)
from app.services.cash_session_service import open_session
from app.services.hotel_service import LUANDA
from app.services.invoice_service import PaymentAmountMismatchError

# Today 10:00 in Luanda - a marcação of the day.
TODAY = datetime.now(LUANDA).replace(hour=10, minute=0, second=0, microsecond=0)


async def _spa(db, ctx):
    """A practitioner type (requires a service), one practitioner, a 60 min massage at 15 000 and a free service."""
    company_id = ctx["company"].id
    practitioner = ResourceTypeCatalog(company_id=company_id, name="Praticante", requires_service=True)
    db.add(practitioner)
    await db.flush()
    ana = Resource(company_id=company_id, activity_id=ctx["activity"].id, resource_type_id=practitioner.id, name="Ana (massagem)")
    massage = Service(company_id=company_id, code="SPA-MAS60", name="Massagem 60 min", price=15000, vat_id=ctx["vat_nor"].id,
                      unit_of_measure_id=ctx["unit_un"].id, resource_type_id=practitioner.id, duration_minutes=60)
    free = Service(company_id=company_id, code="SPA-AVAL", name="Avaliação", price=0, vat_id=ctx["vat_nor"].id,
                   unit_of_measure_id=ctx["unit_un"].id, duration_minutes=30)
    db.add_all([ana, massage, free])
    await db.commit()
    await open_session(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], 0)
    return ana, massage, free


async def _booking(db, ctx, resource, service, starts_at, minutes=60):
    return await create_booking(db, ctx["company"].id, resource.id, ctx["gestor"].id, starts_at,
                                starts_at + timedelta(minutes=minutes), service_id=service.id if service else None,
                                guest_name="Maria")


def _cash(ctx, amount):
    return [{"payment_method_id": ctx["pm_numerario"].id, "amount": amount}]


@pytest.mark.asyncio
async def test_charging_a_marcacao_sells_its_service_and_concludes_it(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, _ = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY)
    booking, invoice = await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id,
                                            _cash(ctx, 17100.0))  # 15 000 + 14 %
    assert booking.status == BookingStatus.CONCLUIDA
    assert booking.invoice_id == invoice.id
    assert float(invoice.total) == 17100.0
    assert invoice.observations.startswith("Cliente: Maria - Ana (massagem)")


@pytest.mark.asyncio
async def test_a_longer_marcacao_charges_the_service_per_started_duration(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, _ = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY, minutes=90)
    _, invoice = await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 34200.0))
    assert float(invoice.total) == 34200.0


@pytest.mark.asyncio
async def test_a_charged_marcacao_keeps_its_slot(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, _ = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY)
    await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))
    with pytest.raises(BookingOverlapError):
        await _booking(db, ctx, ana, massage, TODAY + timedelta(minutes=30))


@pytest.mark.asyncio
async def test_a_wrong_payment_charges_nothing(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, _ = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY)
    with pytest.raises(PaymentAmountMismatchError):
        await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 1000.0))
    await db.rollback()
    await db.refresh(booking)
    assert booking.status == BookingStatus.PENDENTE
    assert booking.invoice_id is None


@pytest.mark.asyncio
async def test_only_a_marcacao_with_a_priced_service_of_today_is_charged(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, free = await _spa(db, ctx)
    unpriced = await _booking(db, ctx, ana, free, TODAY + timedelta(hours=2), minutes=30)
    with pytest.raises(BookingNotChargeableError, match="preço"):
        await charge_booking(db, ctx["company"].id, unpriced.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 0))
    tomorrow = await _booking(db, ctx, ana, massage, TODAY + timedelta(days=1))
    with pytest.raises(BookingNotChargeableError, match="próprio dia"):
        await charge_booking(db, ctx["company"].id, tomorrow.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))
    cancelled = await _booking(db, ctx, ana, massage, TODAY + timedelta(hours=4))
    await update_booking_status(db, ctx["company"].id, cancelled.id, BookingStatus.CANCELADA)
    with pytest.raises(BookingNotChargeableError):
        await charge_booking(db, ctx["company"].id, cancelled.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))
    assert (await db.execute(Invoice.__table__.select().where(Invoice.company_id == ctx["company"].id))).first() is None


@pytest.mark.asyncio
async def test_a_priced_marcacao_is_not_concluded_by_hand(db, company_with_essentials):
    ctx = company_with_essentials
    ana, massage, free = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY)
    with pytest.raises(BookingNotEditableError, match="cobrar"):
        await update_booking_status(db, ctx["company"].id, booking.id, BookingStatus.CONCLUIDA)
    unpriced = await _booking(db, ctx, ana, free, TODAY + timedelta(hours=2), minutes=30)
    unpriced = await update_booking_status(db, ctx["company"].id, unpriced.id, BookingStatus.CONCLUIDA)
    assert unpriced.status == BookingStatus.CONCLUIDA


@pytest.mark.asyncio
async def test_a_hotel_activity_bills_its_bookings_through_the_check_in(db, company_with_essentials):
    from app.models.module_capability import ModuleCapability
    from app.services.activity_service import list_activities
    ctx = company_with_essentials
    ana, massage, _ = await _spa(db, ctx)
    db.add(ModuleCapability(module_id=ctx["activity"].module_id, capability="HOTEL_STAY", is_enabled=True))
    await db.commit()
    activity = next(a for a in await list_activities(db, ctx["company"].id) if a.id == ctx["activity"].id)
    assert activity.capabilities == ["HOTEL_STAY"]
    booking = await _booking(db, ctx, ana, massage, TODAY)
    with pytest.raises(BookingNotChargeableError, match="check-in"):
        await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, 17100.0))


async def _charged_with_its_line(db, ctx, minutes=60):
    from sqlalchemy import select
    from app.models.invoice_line import InvoiceLine
    ana, massage, _ = await _spa(db, ctx)
    booking = await _booking(db, ctx, ana, massage, TODAY, minutes=minutes)
    total = 17100.0 * (minutes // 60)
    booking, invoice = await charge_booking(db, ctx["company"].id, booking.id, ctx["gestor"], ctx["pos"].id, _cash(ctx, total))
    line = (await db.execute(select(InvoiceLine).where(InvoiceLine.invoice_id == invoice.id))).scalar_one()
    return ana, massage, booking, invoice, line


@pytest.mark.asyncio
async def test_a_fully_credited_marcacao_is_cancelled_and_frees_its_slot(db, company_with_essentials):
    from app.services.invoice_service import create_credit_note
    ctx = company_with_essentials
    ana, massage, booking, invoice, line = await _charged_with_its_line(db, ctx)
    await create_credit_note(db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice.id,
                             credit_note_reason="ANL", credit_note_cause="Cliente desistiu",
                             lines_input=[{"invoice_line_id": line.id, "quantity": 1}])
    await db.refresh(booking)
    assert booking.status == BookingStatus.CANCELADA
    assert booking.invoice_id == invoice.id  # the record stays
    await _booking(db, ctx, ana, massage, TODAY + timedelta(minutes=30))  # the slot is free again


@pytest.mark.asyncio
async def test_a_partly_credited_marcacao_stays_paid(db, company_with_essentials):
    from app.services.invoice_service import create_credit_note
    ctx = company_with_essentials
    ana, massage, booking, invoice, line = await _charged_with_its_line(db, ctx, minutes=120)
    await create_credit_note(db, ctx["company"].id, ctx["activity"].id, reference_invoice_id=invoice.id,
                             credit_note_reason="RTF", credit_note_cause="Meia hora a menos",
                             lines_input=[{"invoice_line_id": line.id, "quantity": 1}])
    await db.refresh(booking)
    assert booking.status == BookingStatus.CONCLUIDA
    with pytest.raises(BookingOverlapError):
        await _booking(db, ctx, ana, massage, TODAY + timedelta(minutes=30))
