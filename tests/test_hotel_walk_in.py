"""Hotel point 2, part E: a passage (30 min, 1 h...) is paid before going in - the sale first, then the room occupied
for the service's duration. Its exit records the real time; a stay beyond the planned end shows in the history and
keeps the room occupied on the floor plan."""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.booking import BookingStatus
from app.models.invoice import Invoice
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.models.service import Service
from app.services.booking_service import BookingOverlapError, ServiceRequiredError, create_booking
from app.services.cash_session_service import open_session
from app.services.hotel_service import InvalidWalkInError, check_out, get_occupancy_history, walk_in
from app.services.resource_status_service import list_resource_statuses


async def _rooms(db, ctx):
    """One room, a 1-hour rate (5 000 + 14 % = 5 700) and a night rate (no duration), and the till open."""
    cid = ctx["company"].id
    room_type = ResourceTypeCatalog(company_id=cid, name="Quarto", requires_service=True)
    db.add(room_type)
    await db.flush()
    room = Resource(company_id=cid, activity_id=ctx["activity"].id, resource_type_id=room_type.id, name="Quarto 103")
    hour = Service(company_id=cid, code="PAS-1H", name="Quarto 1 hora", price=5000, vat_id=ctx["vat_nor"].id,
                   unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room_type.id, duration_minutes=60)
    night = Service(company_id=cid, code="PAS-DIA", name="Diária", price=25000, vat_id=ctx["vat_nor"].id,
                    unit_of_measure_id=ctx["unit_un"].id, resource_type_id=room_type.id)
    db.add_all([room, hour, night])
    await db.commit()
    await open_session(db, cid, ctx["pos"].id, ctx["gestor"], 0)
    return room, hour, night


async def _enter(db, ctx, room, service, now=None, amount=5700.0):
    return await walk_in(db, ctx["company"].id, room.id, service.id, ctx["gestor"], ctx["pos"].id,
                         [{"payment_method_id": ctx["pm_numerario"].id, "amount": amount}], guest_name="Passagem", now=now)


async def _invoices(db, ctx):
    return (await db.execute(select(func.count()).select_from(Invoice).where(Invoice.company_id == ctx["company"].id))).scalar_one()


@pytest.mark.asyncio
async def test_a_passage_is_sold_then_occupies_the_room_for_its_duration(db, company_with_essentials):
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    booking, invoice = await _enter(db, ctx, room, hour)
    assert float(invoice.total) == 5700.0
    assert booking.status == BookingStatus.EM_CURSO and booking.invoice_id == invoice.id
    assert booking.ends_at - booking.starts_at == timedelta(minutes=60)
    assert invoice.observations.startswith("Hóspede: Passagem - Quarto 103 - ")  # who, which room, from when to when
    status = (await list_resource_statuses(db, ctx["company"].id, ctx["activity"].id))[0]
    assert status["status"] == "OCUPADA" and status["stay_overdue_minutes"] == 0


@pytest.mark.asyncio
async def test_nothing_is_cashed_for_a_room_already_occupied(db, company_with_essentials):
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    await _enter(db, ctx, room, hour)
    with pytest.raises(BookingOverlapError, match="ocupado"):
        await _enter(db, ctx, room, hour)
    assert await _invoices(db, ctx) == 1


@pytest.mark.asyncio
async def test_a_passage_needs_a_timed_service(db, company_with_essentials):
    ctx = company_with_essentials
    room, _, night = await _rooms(db, ctx)
    with pytest.raises(InvalidWalkInError, match="duração"):
        await _enter(db, ctx, room, night, amount=28500.0)
    assert await _invoices(db, ctx) == 0


@pytest.mark.asyncio
async def test_an_overdue_passage_keeps_the_room_occupied(db, company_with_essentials):
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    await _enter(db, ctx, room, hour, now=datetime.now(timezone.utc) - timedelta(hours=2))  # planned end: an hour ago
    status = (await list_resource_statuses(db, ctx["company"].id, ctx["activity"].id))[0]
    assert status["status"] == "OCUPADA"
    assert status["stay_overdue_minutes"] >= 59


@pytest.mark.asyncio
async def test_the_exit_records_the_time_and_the_overstay_shows_in_the_history(db, company_with_essentials):
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    booking, invoice = await _enter(db, ctx, room, hour, now=datetime.now(timezone.utc) - timedelta(hours=2))
    booking = await check_out(db, ctx["company"].id, booking.id)  # prepaid: nothing left to pay
    assert booking.status == BookingStatus.CONCLUIDA and booking.checked_out_at is not None
    entry = (await get_occupancy_history(db, ctx["company"].id))[0]
    assert entry["invoice_series"] == invoice.series and entry["invoice_total"] == 5700.0
    assert entry["guest_name"] == "Passagem"
    assert entry["overstay_minutes"] >= 59
    status = (await list_resource_statuses(db, ctx["company"].id, ctx["activity"].id))[0]
    assert status["status"] == "LIVRE"


@pytest.mark.asyncio
async def test_a_room_rate_without_price_is_refused_before_anything(db, company_with_essentials):
    """Without a price the check-in would add no line: the stay would cost nothing. Refused at the booking and
    at the entry, before any sale."""
    ctx = company_with_essentials
    room, hour, night = await _rooms(db, ctx)
    hour.price, night.price = None, None
    await db.commit()
    with pytest.raises(ServiceRequiredError, match="não tem preço"):
        await _enter(db, ctx, room, hour)
    start = datetime.now(timezone.utc) + timedelta(days=1)
    with pytest.raises(ServiceRequiredError, match="não tem preço"):
        await create_booking(db, ctx["company"].id, room.id, ctx["gestor"].id, start, start + timedelta(days=1),
                             service_id=night.id)
    assert await _invoices(db, ctx) == 0


@pytest.mark.asyncio
async def test_a_passage_is_invoiced_to_the_customer_who_asks_for_it(db, company_with_essentials):
    """Without a customer the FR goes to Consumidor final; a guest who asks for his NIF on it gets his own."""
    from app.models.customer import Customer, LegalPersonType
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    guest = Customer(company_id=ctx["company"].id, name="Cliente Passagem", nif="5000444555", legal_person_type=LegalPersonType.FISICA)
    db.add(guest)
    await db.commit()
    booking, invoice = await walk_in(db, ctx["company"].id, room.id, hour.id, ctx["gestor"], ctx["pos"].id,
                                     [{"payment_method_id": ctx["pm_numerario"].id, "amount": 5700.0}], customer_id=guest.id)
    assert invoice.customer_id == guest.id and booking.customer_id == guest.id


@pytest.mark.asyncio
async def test_a_room_rate_is_never_sold_alone_in_the_cart(db, company_with_essentials):
    """Sold alone, an hour of room would occupy no room and record no exit: the cart and a table's account refuse
    it; the Entrada and the stay's account (stay sales) remain the only ways to sell it."""
    from app.services.invoice_service import ProductNotFoundError
    from app.services.open_account_service import InvalidLineError, add_line, open_account
    from app.services.pos_service import checkout
    from app.services.service_service import list_services
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    with pytest.raises(ProductNotFoundError, match="Entrada"):
        await checkout(db, ctx["company"].id, ctx["pos"].id, ctx["gestor"], None,
                       [{"product_id": None, "service_id": str(hour.id), "quantity": 1.0, "sale_unit_id": None}],
                       [{"payment_method_id": ctx["pm_numerario"].id, "amount": 5700.0}], invoice_type="FACTURA_RECIBO")
    tab = await open_account(db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, "Balcão")
    with pytest.raises(InvalidLineError, match="Entrada"):
        await add_line(db, ctx["company"].id, tab.id, ctx["gestor"].id, 1, service_id=hour.id)
    assert await _invoices(db, ctx) == 0
    flags = {s.code: s.is_stay_rate for s in await list_services(db, ctx["company"].id)}
    assert flags["PAS-1H"] is True
    await _enter(db, ctx, room, hour)  # the Entrada still sells it
    assert await _invoices(db, ctx) == 1


@pytest.mark.asyncio
async def test_a_company_keeps_the_withholding_of_a_room_rate_that_carries_one(db, company_with_essentials):
    """A room rate with a withholding (6,5 %) sold to a pessoa coletiva: the till collects the total minus the
    withholding (5 700 - 325 = 5 375) - the screens show it; asking for the whole total is refused."""
    from app.models.customer import Customer, LegalPersonType
    from app.models.withholding_tax import WithholdingTax
    from app.services.invoice_service import PaymentAmountMismatchError
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    tax = WithholdingTax(name="Retenção na fonte", rate=6.5, tax_type="II")
    company = Customer(company_id=ctx["company"].id, name="Empresa Hóspede", nif="5000777888", legal_person_type=LegalPersonType.JURIDICA)
    db.add_all([tax, company])
    await db.flush()
    hour.withholding_tax_id = tax.id
    await db.commit()
    with pytest.raises(PaymentAmountMismatchError):
        await walk_in(db, ctx["company"].id, room.id, hour.id, ctx["gestor"], ctx["pos"].id,
                      [{"payment_method_id": ctx["pm_numerario"].id, "amount": 5700.0}], customer_id=company.id)
    booking, invoice = await walk_in(db, ctx["company"].id, room.id, hour.id, ctx["gestor"], ctx["pos"].id,
                                     [{"payment_method_id": ctx["pm_numerario"].id, "amount": 5375.0}], customer_id=company.id)
    assert float(invoice.total) == 5700.0 and float(invoice.retention_total) == 325.0


@pytest.mark.asyncio
async def test_the_final_consumer_never_has_a_withholding(db, company_with_essentials):
    """A Consumidor final (NIF 999999999) is a private person: no withholding, even if it was recorded as a pessoa
    coletiva by an old default - the whole total is cashed. A new final consumer is always recorded as singular."""
    from app.models.customer import Customer, LegalPersonType
    from app.models.withholding_tax import WithholdingTax
    ctx = company_with_essentials
    room, hour, _ = await _rooms(db, ctx)
    tax = WithholdingTax(name="Retenção na fonte", rate=6.5, tax_type="II")
    old = Customer(company_id=ctx["company"].id, name="Família Teste", nif="999999999", is_final_consumer=True,
                   legal_person_type=LegalPersonType.JURIDICA)  # the old wrong default
    db.add_all([tax, old])
    await db.flush()
    hour.withholding_tax_id = tax.id
    await db.commit()
    _, invoice = await walk_in(db, ctx["company"].id, room.id, hour.id, ctx["gestor"], ctx["pos"].id,
                               [{"payment_method_id": ctx["pm_numerario"].id, "amount": 5700.0}], customer_id=old.id)
    assert float(invoice.retention_total or 0) == 0.0


@pytest.mark.asyncio
async def test_a_new_final_consumer_is_recorded_as_a_private_person(db, company_with_essentials):
    from app.models.customer import LegalPersonType
    from app.services.customer_service import create_customer
    new = await create_customer(db, company_with_essentials["company"].id, "Consumidor", "", is_final_consumer=True)
    assert new.legal_person_type == LegalPersonType.FISICA and new.nif == "999999999"
