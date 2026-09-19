"""
Tests for resource_status_service - derived table status (LIVRE / OCUPADA / RESERVADA).
"""
from datetime import datetime, timedelta, timezone

import pytest

from app.models.booking import Booking, BookingStatus
from app.models.open_account import OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.services.open_account_service import open_account
from app.services.resource_status_service import list_resource_statuses

NOW = datetime(2026, 9, 20, 12, 0, tzinfo=timezone.utc)


async def _tables(db, ctx, *names):
    resource_type = ResourceTypeCatalog(company_id=ctx["company"].id, name="Mesa")
    db.add(resource_type)
    await db.flush()
    tables = []
    for name in names:
        table = Resource(
            company_id=ctx["company"].id, activity_id=ctx["activity"].id, resource_type_id=resource_type.id,
            name=name, capacity=4,
        )
        db.add(table)
        tables.append(table)
    await db.commit()
    for table in tables:
        await db.refresh(table)
    return tables


async def _tab(db, ctx, table, *amounts, label=None):
    account = await open_account(
        db, ctx["company"].id, ctx["activity"].id, ctx["pos"].id, ctx["gestor"].id, label or table.name, resource_id=table.id,
    )
    for quantity, price in amounts:
        db.add(OpenAccountLine(
            account_id=account.id, name_snapshot="Artigo", quantity=quantity, unit_price=price, added_by_user_id=ctx["gestor"].id,
        ))
    await db.commit()
    return account


async def _booking(db, ctx, table, start_minutes, duration_minutes, status=BookingStatus.CONFIRMADA):
    booking = Booking(
        company_id=ctx["company"].id, resource_id=table.id, status=status, created_by_user_id=ctx["gestor"].id,
        starts_at=NOW + timedelta(minutes=start_minutes), ends_at=NOW + timedelta(minutes=start_minutes + duration_minutes),
    )
    db.add(booking)
    await db.commit()
    await db.refresh(booking)
    return booking


async def _statuses(db, ctx):
    rows = await list_resource_statuses(db, ctx["company"].id, ctx["activity"].id, now=NOW, window_minutes=60)
    return {r["name"]: r for r in rows}


@pytest.mark.asyncio
async def test_tables_without_accounts_or_bookings_are_free(db, company_with_essentials):
    ctx = company_with_essentials
    await _tables(db, ctx, "Mesa 1", "Mesa 2")
    result = await _statuses(db, ctx)
    assert list(result) == ["Mesa 1", "Mesa 2"]
    assert all(r["status"] == "LIVRE" for r in result.values())
    assert result["Mesa 1"]["capacity"] == 4 and result["Mesa 1"]["open_accounts"] == 0 and result["Mesa 1"]["open_total"] == 0


@pytest.mark.asyncio
async def test_open_accounts_make_the_table_occupied_and_sum_every_account_on_it(db, company_with_essentials):
    ctx = company_with_essentials
    t1, t2 = await _tables(db, ctx, "Mesa 1", "Mesa 2")
    await _tab(db, ctx, t1, (2, 500), (1, 300))
    await _tab(db, ctx, t1, (1, 700), label="Mesa 1 - B")  # a split bill on the same table
    result = await _statuses(db, ctx)
    assert result["Mesa 1"]["status"] == "OCUPADA" and result["Mesa 1"]["open_accounts"] == 2
    assert round(result["Mesa 1"]["open_total"], 2) == 2000.0
    assert result["Mesa 1"]["opened_at"] is not None
    assert result["Mesa 2"]["status"] == "LIVRE"


@pytest.mark.asyncio
async def test_closed_accounts_do_not_occupy_the_table(db, company_with_essentials):
    ctx = company_with_essentials
    (t1,) = await _tables(db, ctx, "Mesa 1")
    account = await _tab(db, ctx, t1, (1, 500))
    account.status = OpenAccountStatus.FECHADA
    await db.commit()
    result = await _statuses(db, ctx)
    assert result["Mesa 1"]["status"] == "LIVRE" and result["Mesa 1"]["open_accounts"] == 0


@pytest.mark.asyncio
async def test_active_bookings_inside_the_window_reserve_the_table(db, company_with_essentials):
    ctx = company_with_essentials
    t1, t2, t3, t4 = await _tables(db, ctx, "Mesa 1", "Mesa 2", "Mesa 3", "Mesa 4")
    await _booking(db, ctx, t1, -30, 90)                              # running now
    await _booking(db, ctx, t2, 30, 60)                               # starts within the window
    await _booking(db, ctx, t3, 180, 60)                              # starts in 3 hours
    await _booking(db, ctx, t4, -30, 90, status=BookingStatus.CANCELADA)  # cancelled bookings hold nothing
    result = await _statuses(db, ctx)
    assert result["Mesa 1"]["status"] == "RESERVADA" and result["Mesa 1"]["booking_status"] == "CONFIRMADA"
    assert result["Mesa 1"]["booking_id"] is not None and result["Mesa 1"]["booking_starts_at"] is not None
    assert result["Mesa 2"]["status"] == "RESERVADA"
    assert result["Mesa 3"]["status"] == "LIVRE" and result["Mesa 3"]["booking_id"] is None
    assert result["Mesa 4"]["status"] == "LIVRE"


@pytest.mark.asyncio
async def test_occupied_wins_over_reserved_but_the_booking_is_still_reported(db, company_with_essentials):
    ctx = company_with_essentials
    (t1,) = await _tables(db, ctx, "Mesa 1")
    await _tab(db, ctx, t1, (1, 500))
    await _booking(db, ctx, t1, 20, 60)
    result = await _statuses(db, ctx)
    assert result["Mesa 1"]["status"] == "OCUPADA"
    assert result["Mesa 1"]["booking_id"] is not None


@pytest.mark.asyncio
async def test_inactive_resources_are_excluded(db, company_with_essentials):
    ctx = company_with_essentials
    t1, t2 = await _tables(db, ctx, "Mesa 1", "Mesa 2")
    t2.is_active = False
    await db.commit()
    result = await _statuses(db, ctx)
    assert list(result) == ["Mesa 1"]
