"""
Kitchen screen (point 34c). The kitchen sees the orders sent from the open accounts (KitchenOrder), one card per
order, and moves each dish forward: EM_ESPERA -> EM_PREPARACAO -> PRONTO, or refuses it (ANULADO, 'Esgotado').
An order leaves the screen once none of its dishes waits or is being prepared; the last ones stay reachable.
A dish of an account already closed (so already invoiced) may still be marked ready, never cancelled nor lowered.
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.kitchen_order import KitchenOrder
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.user import User
from app.services.open_account_service import (
    KITCHEN_CANCELLED, KITCHEN_PREPARING, KITCHEN_READY, KITCHEN_WAITING, InvalidLineError, _QTY_EPS, _cancel_line,
)

ACTIVE = (KITCHEN_WAITING, KITCHEN_PREPARING)
RECENT_COUNT = 5


class KitchenItemNotFoundError(Exception):
    pass


async def _cards(db: AsyncSession, order_ids: list[uuid.UUID]) -> list[dict]:
    """The cards of these orders, oldest first: number, table, activity, sender, time, and every dish of the order."""
    if not order_ids:
        return []
    rows = (await db.execute(
        select(KitchenOrder, OpenAccount.label, Activity.name, User.full_name)
        .join(OpenAccount, OpenAccount.id == KitchenOrder.account_id)
        .join(Activity, Activity.id == OpenAccount.activity_id)
        .join(User, User.id == KitchenOrder.sent_by_user_id)
        .where(KitchenOrder.id.in_(order_ids))
        .order_by(KitchenOrder.sent_at)
    )).all()
    lines = (await db.execute(
        select(OpenAccountLine).where(OpenAccountLine.kitchen_order_id.in_(order_ids)).order_by(OpenAccountLine.added_at)
    )).scalars().all()
    by_order: dict[uuid.UUID, list[dict]] = {}
    for line in lines:
        by_order.setdefault(line.kitchen_order_id, []).append({
            "id": line.id, "name": line.name_snapshot, "quantity": float(line.quantity),
            "unit_code": line.unit_code_snapshot, "status": line.kitchen_status,
            "modified": bool(line.kitchen_modified), "cancel_reason": line.cancel_reason,
        })
    return [
        {
            "id": order.id, "number": order.number, "account_label": label, "activity_name": activity,
            "sent_by_name": sender, "sent_at": order.sent_at, "lines": by_order.get(order.id, []),
        }
        for order, label, activity, sender in rows
    ]


async def kitchen_board(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The orders still in the kitchen (a dish waiting or being prepared), oldest first, and the last ones done
    today, newest first."""
    active_ids = (await db.execute(
        select(OpenAccountLine.kitchen_order_id).distinct()
        .join(KitchenOrder, KitchenOrder.id == OpenAccountLine.kitchen_order_id)
        .where(KitchenOrder.company_id == company_id, OpenAccountLine.kitchen_status.in_(ACTIVE))
    )).scalars().all()
    recent_query = select(KitchenOrder.id).where(KitchenOrder.company_id == company_id, KitchenOrder.day == date.today())
    if active_ids:
        recent_query = recent_query.where(KitchenOrder.id.not_in(active_ids))
    recent_ids = (await db.execute(recent_query.order_by(KitchenOrder.sent_at.desc()).limit(RECENT_COUNT))).scalars().all()
    recent = await _cards(db, list(recent_ids))
    recent.reverse()  # _cards gives the oldest first: the strip shows the newest first
    return {"orders": await _cards(db, list(active_ids)), "recent": recent}


async def _line_or_raise(db: AsyncSession, company_id: uuid.UUID, line_id: uuid.UUID) -> tuple[OpenAccountLine, bool]:
    """The dish (locked) and whether its account is already closed - only a dish sent by this company."""
    row = (await db.execute(
        select(OpenAccountLine, OpenAccount.status)
        .join(KitchenOrder, KitchenOrder.id == OpenAccountLine.kitchen_order_id)
        .join(OpenAccount, OpenAccount.id == OpenAccountLine.account_id)
        .where(OpenAccountLine.id == line_id, KitchenOrder.company_id == company_id)
        .with_for_update(of=OpenAccountLine)
    )).first()
    if row is None:
        raise KitchenItemNotFoundError("Prato nao encontrado na cozinha")
    line, account_status = row
    return line, account_status == OpenAccountStatus.FECHADA


def _stamp_start(line: OpenAccountLine, user_id: uuid.UUID | None) -> None:
    line.kitchen_status = KITCHEN_PREPARING
    line.started_at = func.now()
    line.started_by_user_id = user_id


def _stamp_ready(line: OpenAccountLine, user_id: uuid.UUID | None) -> None:
    line.kitchen_status = KITCHEN_READY
    line.ready_at = func.now()
    line.ready_by_user_id = user_id


def _apply(line: OpenAccountLine, account_closed: bool, action: str, quantity: float | None = None,
           user_id: uuid.UUID | None = None) -> None:
    if line.kitchen_status not in ACTIVE:
        raise InvalidLineError("Este prato ja nao esta em preparacao na cozinha")
    if action == "start":
        if line.kitchen_status != KITCHEN_WAITING:
            raise InvalidLineError("Este prato ja esta em preparacao")
        _stamp_start(line, user_id)
    elif action == "ready":
        _stamp_ready(line, user_id)
    elif action in ("refuse", "quantity"):
        if account_closed:
            raise InvalidLineError("A conta ja foi fechada - este prato ja foi faturado")
        if action == "refuse":
            _cancel_line(line, "Esgotado - cozinha", user_id)
        else:
            if quantity is None or quantity <= 0 or float(quantity) - float(line.quantity) > -_QTY_EPS:
                raise InvalidLineError("A cozinha so pode baixar a quantidade de um prato")
            line.quantity = quantity
            line.kitchen_modified = True
    else:
        raise InvalidLineError("Acao desconhecida")


async def act_on_line(db: AsyncSession, company_id: uuid.UUID, line_id: uuid.UUID, action: str,
                      quantity: float | None = None, user_id: uuid.UUID | None = None) -> dict:
    line, account_closed = await _line_or_raise(db, company_id, line_id)
    _apply(line, account_closed, action, quantity, user_id)
    await db.commit()
    return await kitchen_board(db, company_id)


async def act_on_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, action: str,
                       user_id: uuid.UUID | None = None) -> dict:
    """start_all: every waiting dish goes to preparation; ready_all: every dish still in the kitchen is ready."""
    order = (await db.execute(
        select(KitchenOrder).where(KitchenOrder.id == order_id, KitchenOrder.company_id == company_id)
    )).scalar_one_or_none()
    if order is None:
        raise KitchenItemNotFoundError("Pedido nao encontrado na cozinha")
    wanted = {"start_all": (KITCHEN_WAITING,), "ready_all": ACTIVE}.get(action)
    if wanted is None:
        raise InvalidLineError("Acao desconhecida")
    lines = (await db.execute(
        select(OpenAccountLine).where(OpenAccountLine.kitchen_order_id == order.id, OpenAccountLine.kitchen_status.in_(wanted))
        .with_for_update()
    )).scalars().all()
    for line in lines:
        if action == "start_all":
            _stamp_start(line, user_id)
        else:
            _stamp_ready(line, user_id)
    await db.commit()
    return await kitchen_board(db, company_id)


# ---------------------------------------------------------------------------------------------------------------
# History (point 34d): the orders of a period, every dish with who started it, who made it ready, who cancelled it
# and why, and how long it took. Orders sent before the traces existed simply show no duration.

MAX_HISTORY_DAYS = 92


def _minutes(start, end) -> float | None:
    if start is None or end is None:
        return None
    return round((end - start).total_seconds() / 60, 1)


async def kitchen_history(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date) -> dict:
    if date_to < date_from:
        raise InvalidLineError("A data final e anterior a data inicial")
    if (date_to - date_from).days >= MAX_HISTORY_DAYS:
        raise InvalidLineError(f"O periodo nao pode ultrapassar {MAX_HISTORY_DAYS} dias")
    order_ids = (await db.execute(
        select(KitchenOrder.id).where(
            KitchenOrder.company_id == company_id, KitchenOrder.day >= date_from, KitchenOrder.day <= date_to,
        )
    )).scalars().all()
    cards = await _cards(db, list(order_ids))
    lines = (await db.execute(
        select(OpenAccountLine).where(OpenAccountLine.kitchen_order_id.in_(order_ids))
    )).scalars().all() if order_ids else []
    user_ids = {u for l in lines for u in (l.started_by_user_id, l.ready_by_user_id, l.cancelled_by_user_id) if u}
    names = dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(user_ids)))).all()) if user_ids else {}
    by_id = {l.id: l for l in lines}

    served = cancelled = sold_out = 0
    waits: list[float] = []
    for card in cards:
        ready_times = []
        for dish in card["lines"]:
            line = by_id[dish["id"]]
            dish.update({
                "started_at": line.started_at, "started_by_name": names.get(line.started_by_user_id),
                "ready_at": line.ready_at, "ready_by_name": names.get(line.ready_by_user_id),
                "cancelled_at": line.cancelled_at, "cancelled_by_name": names.get(line.cancelled_by_user_id),
                "prep_minutes": _minutes(line.started_at, line.ready_at),
                "wait_minutes": _minutes(card["sent_at"], line.ready_at),
            })
            if line.kitchen_status == KITCHEN_READY:
                served += 1
                if line.ready_at is not None:
                    ready_times.append(line.ready_at)
                    waits.append(dish["wait_minutes"])
            elif line.kitchen_status == KITCHEN_CANCELLED:
                cancelled += 1
                if (line.cancel_reason or "").startswith("Esgotado"):
                    sold_out += 1
        card["dishes"] = sum(1 for d in card["lines"] if d["status"] != KITCHEN_CANCELLED)
        card["cancelled"] = sum(1 for d in card["lines"] if d["status"] == KITCHEN_CANCELLED)
        done = all(d["status"] in (KITCHEN_READY, KITCHEN_CANCELLED) for d in card["lines"])
        card["total_minutes"] = _minutes(card["sent_at"], max(ready_times)) if done and ready_times else None
    cards.reverse()  # the newest first
    return {
        "summary": {
            "orders": len(cards), "served": served, "cancelled": cancelled, "sold_out": sold_out,
            "average_wait_minutes": round(sum(waits) / len(waits), 1) if waits else None,
        },
        "orders": cards,
    }
