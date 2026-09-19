"""
Tests for Booking.guest_name / party_size - free-text guest details kept apart from the
fiscal Customer link (a table booked for "Familia Silva - 6" needs no Customer record).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.services.booking_service import create_booking, reschedule_booking
from app.services.resource_status_service import list_resource_statuses

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


async def _table(db, ctx, name="Mesa 1"):
    resource_type = ResourceTypeCatalog(company_id=ctx["company"].id, name="Mesa")
    db.add(resource_type)
    await db.flush()
    table = Resource(
        company_id=ctx["company"].id, activity_id=ctx["activity"].id, resource_type_id=resource_type.id,
        name=name, capacity=4,
    )
    db.add(table)
    await db.commit()
    await db.refresh(table)
    return table


@pytest.mark.asyncio
async def test_guest_name_and_party_size_are_stored_without_a_customer(db, company_with_essentials):
    ctx = company_with_essentials
    table = await _table(db, ctx)
    booking = await create_booking(
        db, ctx["company"].id, table.id, ctx["gestor"].id, NOW + timedelta(hours=2), NOW + timedelta(hours=4),
        guest_name="  Familia Silva  ", party_size=6,
    )
    assert booking.guest_name == "Familia Silva" and booking.party_size == 6 and booking.customer_id is None


@pytest.mark.asyncio
async def test_blank_guest_name_is_stored_as_null(db, company_with_essentials):
    ctx = company_with_essentials
    table = await _table(db, ctx)
    booking = await create_booking(
        db, ctx["company"].id, table.id, ctx["gestor"].id, NOW + timedelta(hours=2), NOW + timedelta(hours=4),
        guest_name="   ",
    )
    assert booking.guest_name is None and booking.party_size is None


@pytest.mark.asyncio
async def test_reschedule_replaces_and_clears_the_guest_details(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    table = await _table(db, ctx)
    start, end = NOW + timedelta(hours=2), NOW + timedelta(hours=4)
    booking = await create_booking(db, company_id, table.id, user_id, start, end, guest_name="Silva", party_size=4)
    booking_id = booking.id

    updated = await reschedule_booking(db, company_id, booking_id, start, end, guest_name="Costa", party_size=2)
    assert updated.guest_name == "Costa" and updated.party_size == 2

    cleared = await reschedule_booking(db, company_id, booking_id, start, end)
    assert cleared.guest_name is None and cleared.party_size is None


@pytest.mark.asyncio
async def test_status_reports_the_guest_details_of_the_reserving_booking(db, company_with_essentials):
    ctx = company_with_essentials
    table = await _table(db, ctx)
    await create_booking(
        db, ctx["company"].id, table.id, ctx["gestor"].id, NOW + timedelta(minutes=30), NOW + timedelta(minutes=120),
        guest_name="Familia Silva", party_size=6,
    )
    rows = await list_resource_statuses(db, ctx["company"].id, ctx["activity"].id, now=NOW, window_minutes=60)
    assert len(rows) == 1 and rows[0]["status"] == "RESERVADA"
    assert rows[0]["booking_guest_name"] == "Familia Silva" and rows[0]["booking_party_size"] == 6
