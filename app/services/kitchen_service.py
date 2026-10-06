"""
Kitchen screen (point 34c). The kitchen sees the orders sent from the open accounts (KitchenOrder), one card per
order, and moves each dish forward: EM_ESPERA -> EM_PREPARACAO -> PRONTO, or refuses it (ANULADO, 'Esgotado').
An order leaves the screen once none of its dishes waits or is being prepared; the last ones stay reachable.
A dish of an account already closed (so already invoiced) may still be marked ready, never cancelled nor lowered.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.kitchen_order import KitchenOrder
from app.models.open_account import OpenAccount, OpenAccountStatus
from app.models.open_account_line import OpenAccountLine
from app.models.user import User
from app.services.open_account_service import (
    KITCHEN_PREPARING, KITCHEN_READY, KITCHEN_WAITING, InvalidLineError, _QTY_EPS, _cancel_line,
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


def _apply(line: OpenAccountLine, account_closed: bool, action: str, quantity: float | None = None) -> None:
    if line.kitchen_status not in ACTIVE:
        raise InvalidLineError("Este prato ja nao esta em preparacao na cozinha")
    if action == "start":
        if line.kitchen_status != KITCHEN_WAITING:
            raise InvalidLineError("Este prato ja esta em preparacao")
        line.kitchen_status = KITCHEN_PREPARING
    elif action == "ready":
        line.kitchen_status = KITCHEN_READY
    elif action in ("refuse", "quantity"):
        if account_closed:
            raise InvalidLineError("A conta ja foi fechada - este prato ja foi faturado")
        if action == "refuse":
            _cancel_line(line, "Esgotado - cozinha")
        else:
            if quantity is None or quantity <= 0 or float(quantity) - float(line.quantity) > -_QTY_EPS:
                raise InvalidLineError("A cozinha so pode baixar a quantidade de um prato")
            line.quantity = quantity
            line.kitchen_modified = True
    else:
        raise InvalidLineError("Acao desconhecida")


async def act_on_line(db: AsyncSession, company_id: uuid.UUID, line_id: uuid.UUID, action: str,
                      quantity: float | None = None) -> dict:
    line, account_closed = await _line_or_raise(db, company_id, line_id)
    _apply(line, account_closed, action, quantity)
    await db.commit()
    return await kitchen_board(db, company_id)


async def act_on_order(db: AsyncSession, company_id: uuid.UUID, order_id: uuid.UUID, action: str) -> dict:
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
        line.kitchen_status = KITCHEN_PREPARING if action == "start_all" else KITCHEN_READY
    await db.commit()
    return await kitchen_board(db, company_id)
