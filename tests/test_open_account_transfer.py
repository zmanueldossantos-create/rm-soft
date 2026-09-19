"""
Tests for open_account_service.transfer_lines - table transfer and bill split.
Lines are inserted directly (no product/service) so these tests only depend on the
open-account models.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select

from app.models.booking import Booking
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.open_account_transfer import OpenAccountTransfer
from app.models.point_of_sale import PointOfSale
from app.models.resource import Resource
from app.models.resource_type_catalog import ResourceTypeCatalog
from app.services.open_account_service import (
    open_account, transfer_lines, remove_line, AccountAlreadyClosedError, InvalidTransferError, ItemNotFoundError,
)


async def _account(db, ctx, label, pos=None, resource_id=None):
    return await open_account(
        db, ctx["company"].id, ctx["activity"].id, (pos or ctx["pos"]).id, ctx["gestor"].id, label, resource_id=resource_id,
    )


async def _line(db, ctx, account, name, quantity, price):
    line = OpenAccountLine(
        account_id=account.id, name_snapshot=name, quantity=quantity, unit_price=price, added_by_user_id=ctx["gestor"].id,
    )
    db.add(line)
    await db.commit()
    await db.refresh(line)
    return line


async def _resource(db, ctx, name="Mesa 9"):
    resource_type = ResourceTypeCatalog(company_id=ctx["company"].id, name="Mesa")
    db.add(resource_type)
    await db.flush()
    resource = Resource(company_id=ctx["company"].id, activity_id=ctx["activity"].id, resource_type_id=resource_type.id, name=name)
    db.add(resource)
    await db.commit()
    await db.refresh(resource)
    return resource


async def _total(db, account_ids):
    rows = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id.in_(account_ids)))).scalars().all()
    return round(sum(float(l.quantity) * float(l.unit_price) for l in rows), 2)


@pytest.mark.asyncio
async def test_full_transfer_moves_the_line_and_closes_the_emptied_source(db, company_with_essentials):
    ctx = company_with_essentials
    src = await _account(db, ctx, "Mesa 1")
    dst = await _account(db, ctx, "Mesa 2")
    line = await _line(db, ctx, src, "Cerveja", 3, 500)
    lines_before = (await db.execute(select(func.count()).select_from(OpenAccountLine))).scalar_one()

    source, target, closed = await transfer_lines(
        db, ctx["company"].id, src.id, ctx["gestor"].id, [{"line_id": line.id, "quantity": 3}], target_account_id=dst.id,
    )

    assert closed is True
    assert source.status == OpenAccountStatus.FECHADA and source.closed_at is not None and source.invoice_id is None
    assert target.status == OpenAccountStatus.ABERTA
    await db.refresh(line)
    assert line.account_id == dst.id and float(line.quantity) == 3
    # nothing was deleted: same number of lines, one audit row
    assert (await db.execute(select(func.count()).select_from(OpenAccountLine))).scalar_one() == lines_before
    audit = (await db.execute(select(OpenAccountTransfer))).scalars().all()
    assert len(audit) == 1
    assert audit[0].source_account_id == src.id and audit[0].target_account_id == dst.id
    assert audit[0].source_line_id == line.id and audit[0].target_line_id == line.id
    assert float(audit[0].quantity) == 3


@pytest.mark.asyncio
async def test_partial_transfer_splits_the_line_and_keeps_the_total(db, company_with_essentials):
    ctx = company_with_essentials
    src = await _account(db, ctx, "Mesa 1")
    dst = await _account(db, ctx, "Mesa 2")
    line = await _line(db, ctx, src, "Prato do dia", 4, 2500)
    total_before = await _total(db, [src.id, dst.id])

    source, target, closed = await transfer_lines(
        db, ctx["company"].id, src.id, ctx["gestor"].id, [{"line_id": line.id, "quantity": 1.5}], target_account_id=dst.id,
    )

    assert closed is False and source.status == OpenAccountStatus.ABERTA
    await db.refresh(line)
    assert float(line.quantity) == 2.5 and line.account_id == src.id
    moved = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == dst.id))).scalars().all()
    assert len(moved) == 1 and moved[0].id != line.id
    assert float(moved[0].quantity) == 1.5 and float(moved[0].unit_price) == 2500 and moved[0].name_snapshot == "Prato do dia"
    assert await _total(db, [src.id, dst.id]) == total_before
    audit = (await db.execute(select(OpenAccountTransfer))).scalars().all()
    assert len(audit) == 1 and audit[0].source_line_id == line.id and audit[0].target_line_id == moved[0].id


@pytest.mark.asyncio
async def test_split_creates_a_new_account_on_the_same_table(db, company_with_essentials):
    ctx = company_with_essentials
    table = await _resource(db, ctx, "Mesa 9")
    src = await _account(db, ctx, "Mesa 9", resource_id=table.id)
    await _line(db, ctx, src, "Sumo", 2, 300)
    cake = await _line(db, ctx, src, "Bolo", 1, 700)

    source, target, closed = await transfer_lines(
        db, ctx["company"].id, src.id, ctx["gestor"].id, [{"line_id": cake.id, "quantity": 1}], new_label="Mesa 9 - B",
    )

    assert closed is False and source.status == OpenAccountStatus.ABERTA
    assert target.id != src.id and target.label == "Mesa 9 - B" and target.status == OpenAccountStatus.ABERTA
    assert target.resource_id == table.id and target.pos_id == src.pos_id and target.activity_id == src.activity_id


@pytest.mark.asyncio
async def test_transfer_to_a_free_table_creates_the_account_named_after_it(db, company_with_essentials):
    ctx = company_with_essentials
    free_table = await _resource(db, ctx, "Mesa 5")
    src = await _account(db, ctx, "Mesa 1")
    line = await _line(db, ctx, src, "Cerveja", 2, 500)

    source, target, closed = await transfer_lines(
        db, ctx["company"].id, src.id, ctx["gestor"].id, [{"line_id": line.id, "quantity": 2}], target_resource_id=free_table.id,
    )

    assert closed is True and source.status == OpenAccountStatus.FECHADA
    assert target.resource_id == free_table.id and target.label == "Mesa 5" and target.status == OpenAccountStatus.ABERTA


@pytest.mark.asyncio
async def test_invalid_transfers_change_nothing(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    src = await _account(db, ctx, "Mesa 1")
    dst = await _account(db, ctx, "Mesa 2")
    line = await _line(db, ctx, src, "Cerveja", 2, 500)
    foreign = await _line(db, ctx, dst, "Agua", 1, 100)
    other_pos = PointOfSale(company_id=company_id, activity_id=ctx["activity"].id, name="Caixa 2", is_default=False)
    db.add(other_pos)
    await db.commit()
    await db.refresh(other_pos)
    bar = await _account(db, ctx, "Bar 1", pos=other_pos)
    src_id, dst_id, bar_id, line_id, foreign_id = src.id, dst.id, bar.id, line.id, foreign.id

    async def attempt(exc, items, **target):
        with pytest.raises(exc):
            await transfer_lines(db, company_id, src_id, user_id, items, **target)

    one = [{"line_id": line_id, "quantity": 1}]
    await attempt(InvalidTransferError, [{"line_id": line_id, "quantity": 3}], target_account_id=dst_id)  # more than available
    await attempt(InvalidTransferError, [{"line_id": line_id, "quantity": 0}], target_account_id=dst_id)  # zero
    await attempt(InvalidTransferError, [], target_account_id=dst_id)                                     # nothing selected
    await attempt(InvalidTransferError, one + one, target_account_id=dst_id)                              # same line twice
    await attempt(InvalidTransferError, one, target_account_id=src_id)                                    # same account
    await attempt(InvalidTransferError, one)                                                              # no destination at all
    await attempt(InvalidTransferError, one, target_account_id=bar_id)                                    # other point of sale
    await attempt(ItemNotFoundError, [{"line_id": foreign_id, "quantity": 1}], target_account_id=bar_id)  # line of another account

    rows = (await db.execute(select(OpenAccountLine.id, OpenAccountLine.account_id, OpenAccountLine.quantity))).all()
    state = {r[0]: (r[1], float(r[2])) for r in rows}
    assert state[line_id] == (src_id, 2.0) and state[foreign_id] == (dst_id, 1.0)
    assert (await db.execute(select(func.count()).select_from(OpenAccountTransfer))).scalar_one() == 0
    assert (await db.execute(select(func.count()).select_from(OpenAccount))).scalar_one() == 3  # no stray account created


@pytest.mark.asyncio
async def test_hotel_stay_accounts_are_refused_in_both_directions(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    room = await _resource(db, ctx, "Quarto 1")
    now = datetime.now(timezone.utc)
    booking = Booking(company_id=company_id, resource_id=room.id, starts_at=now, ends_at=now + timedelta(days=1), created_by_user_id=user_id)
    db.add(booking)
    await db.commit()
    await db.refresh(booking)

    stay = await _account(db, ctx, "Quarto 1")
    stay.booking_id = booking.id
    await db.commit()
    stay_line = await _line(db, ctx, stay, "Minibar", 1, 900)
    normal = await _account(db, ctx, "Mesa 1")
    normal_line = await _line(db, ctx, normal, "Cerveja", 1, 500)
    stay_id, stay_line_id, normal_id, normal_line_id = stay.id, stay_line.id, normal.id, normal_line.id

    with pytest.raises(InvalidTransferError):
        await transfer_lines(db, company_id, stay_id, user_id, [{"line_id": stay_line_id, "quantity": 1}], new_label="Outra")
    with pytest.raises(InvalidTransferError):
        await transfer_lines(db, company_id, normal_id, user_id, [{"line_id": normal_line_id, "quantity": 1}], target_account_id=stay_id)


@pytest.mark.asyncio
async def test_closed_accounts_are_refused(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    src = await _account(db, ctx, "Mesa 1")
    dst = await _account(db, ctx, "Mesa 2")
    line = await _line(db, ctx, src, "Cerveja", 2, 500)
    src_id, dst_id, line_id = src.id, dst.id, line.id
    items = [{"line_id": line_id, "quantity": 1}]

    dst.status = OpenAccountStatus.FECHADA
    await db.commit()
    with pytest.raises(AccountAlreadyClosedError):
        await transfer_lines(db, company_id, src_id, user_id, items, target_account_id=dst_id)

    src.status = OpenAccountStatus.FECHADA
    await db.commit()
    with pytest.raises(AccountAlreadyClosedError):
        await transfer_lines(db, company_id, src_id, user_id, items, new_label="Nova")


@pytest.mark.asyncio
async def test_removing_a_transferred_line_is_not_blocked_and_keeps_the_audit_row(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    src = await _account(db, ctx, "Mesa 1")
    dst = await _account(db, ctx, "Mesa 2")
    line = await _line(db, ctx, src, "Cerveja", 3, 500)
    src_id, dst_id, line_id = src.id, dst.id, line.id

    await transfer_lines(db, company_id, src_id, user_id, [{"line_id": line_id, "quantity": 1}], target_account_id=dst_id)
    moved = (await db.execute(select(OpenAccountLine).where(OpenAccountLine.account_id == dst_id))).scalars().one()
    moved_id = moved.id

    await remove_line(db, company_id, dst_id, moved_id)  # the customer changes their mind

    assert (await db.execute(select(OpenAccountLine).where(OpenAccountLine.id == moved_id))).scalar_one_or_none() is None
    audit = (await db.execute(select(OpenAccountTransfer))).scalars().all()
    assert len(audit) == 1 and audit[0].target_line_id == moved_id and float(audit[0].quantity) == 1
