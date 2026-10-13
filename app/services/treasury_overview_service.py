"""
Tesouraria - the company's cash seen from above, for the manager: a read of what the tills record, nothing stored.

- position: every active till now - open (by whom, since when, the cash expected in its drawer) or closed (the cash
  counted at its last closing, still in the drawer: it opens the next session) - and the transfers in transit;
- movements: the transfers, entradas and saídas of a period, with their tills, reason, state and people;
- closings: the closed sessions of a period, with expected, counted, difference and reason.

The operations themselves are made at the till (Caixa), never here.
"""
import uuid
from datetime import date

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.cash_movement import CashMovement, CashMovementStatus, CashMovementType
from app.models.cash_movement_reason import CashMovementReason
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.point_of_sale import PointOfSale
from app.models.user import User
from app.services.cash_session_service import get_carry_forward_amount, get_current_expected_cash_balance


def _money(value) -> float | None:
    return round(float(value), 2) if value is not None else None


async def _user_names(db: AsyncSession, user_ids) -> dict:
    ids = {u for u in user_ids if u}
    if not ids:
        return {}
    return dict((await db.execute(select(User.id, User.full_name).where(User.id.in_(ids)))).all())


async def _tills(db: AsyncSession, company_id: uuid.UUID, active_only: bool) -> dict:
    """{pos_id: (pos, activity_name)} - the company's tills, by activity then name."""
    query = (select(PointOfSale, Activity.name).join(Activity, Activity.id == PointOfSale.activity_id)
             .where(PointOfSale.company_id == company_id))
    if active_only:
        query = query.where(PointOfSale.is_active.is_(True))
    rows = (await db.execute(query.order_by(Activity.name, PointOfSale.is_default.desc(), PointOfSale.name))).all()
    return {pos.id: (pos, activity_name) for pos, activity_name in rows}


async def get_treasury_position(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """{tills: [...], totals: {cash, in_transit, open_tills, tills}} - the cash of every active till right now."""
    tills = await _tills(db, company_id, active_only=True)
    open_sessions = {s.pos_id: s for s in (await db.execute(
        select(CashSession).where(CashSession.company_id == company_id, CashSession.status == CashSessionStatus.ABERTA)
    )).scalars().all()}
    pending = (await db.execute(
        select(CashMovement).where(CashMovement.company_id == company_id, CashMovement.status == CashMovementStatus.PENDENTE)
    )).scalars().all()
    last_closed_at = dict((await db.execute(
        select(CashSession.pos_id, func.max(CashSession.closed_at))
        .where(CashSession.company_id == company_id, CashSession.status == CashSessionStatus.FECHADA)
        .group_by(CashSession.pos_id)
    )).all())
    names = await _user_names(db, [s.opened_by_user_id for s in open_sessions.values()])

    rows = []
    for pos_id, (pos, activity_name) in tills.items():
        session = open_sessions.get(pos_id)
        if session is not None:
            cash = await get_current_expected_cash_balance(db, company_id, pos_id, session)
        else:
            cash = await get_carry_forward_amount(db, company_id, pos_id)  # counted at the last closing, still there
        rows.append({
            "pos_id": pos_id, "pos_name": pos.name, "activity_name": activity_name, "is_default": pos.is_default,
            "billetage_enabled": pos.billetage_enabled,
            "is_open": session is not None,
            "session_id": session.id if session else None,
            "business_date": session.business_date if session else None,
            "opened_at": session.opened_at if session else None,
            "opened_by": names.get(session.opened_by_user_id) if session else None,
            "last_closed_at": last_closed_at.get(pos_id),
            "cash": round(cash, 2),
            "pending_out": round(sum(float(m.amount) for m in pending if m.source_pos_id == pos_id), 2),
            "pending_in": round(sum(float(m.amount) for m in pending if m.destination_pos_id == pos_id), 2),
        })
    return {
        "tills": rows,
        "totals": {
            "cash": round(sum(r["cash"] for r in rows), 2),
            "in_transit": round(sum(float(m.amount) for m in pending), 2),
            "open_tills": sum(1 for r in rows if r["is_open"]),
            "tills": len(rows),
        },
    }


async def list_treasury_movements(
    db: AsyncSession, company_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
    pos_id: uuid.UUID | None = None, movement_type: CashMovementType | None = None,
    status: CashMovementStatus | None = None, limit: int = 500,
) -> list[dict]:
    """The movements of a period (by their date), most recent first - a till filter matches either side."""
    query = select(CashMovement).where(CashMovement.company_id == company_id)
    if date_from is not None:
        query = query.where(CashMovement.movement_date >= date_from)
    if date_to is not None:
        query = query.where(CashMovement.movement_date <= date_to)
    if pos_id is not None:
        query = query.where(or_(CashMovement.source_pos_id == pos_id, CashMovement.destination_pos_id == pos_id))
    if movement_type is not None:
        query = query.where(CashMovement.movement_type == movement_type)
    if status is not None:
        query = query.where(CashMovement.status == status)
    movements = (await db.execute(
        query.order_by(CashMovement.movement_date.desc(), CashMovement.created_at.desc()).limit(limit)
    )).scalars().all()

    tills = await _tills(db, company_id, active_only=False)
    reasons = dict((await db.execute(
        select(CashMovementReason.id, CashMovementReason.name).where(CashMovementReason.company_id == company_id)
    )).all())
    names = await _user_names(db, [m.created_by_user_id for m in movements] + [m.received_by_user_id for m in movements])

    def till(pos_id):
        return {"id": pos_id, "name": tills[pos_id][0].name, "activity_name": tills[pos_id][1]} if pos_id in tills else None

    return [{
        "id": m.id, "movement_type": m.movement_type.value, "status": m.status.value,
        "movement_date": m.movement_date, "created_at": m.created_at, "amount": _money(m.amount),
        "source": till(m.source_pos_id), "destination": till(m.destination_pos_id),
        "reason": reasons.get(m.reason_id), "description": m.description,
        "created_by": names.get(m.created_by_user_id),
        # an entrada or saída is "received" at its creation by its own author: only a transfer has a receiver
        "received_by": names.get(m.received_by_user_id) if m.movement_type == CashMovementType.TRANSFERENCIA else None,
        "received_at": m.received_at if m.movement_type == CashMovementType.TRANSFERENCIA else None,
    } for m in movements]


async def list_closings(
    db: AsyncSession, company_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
    pos_id: uuid.UUID | None = None, limit: int = 500,
) -> list[dict]:
    """The closed sessions of a period (by their business day), most recent first."""
    query = select(CashSession).where(CashSession.company_id == company_id, CashSession.status == CashSessionStatus.FECHADA)
    if date_from is not None:
        query = query.where(CashSession.business_date >= date_from)
    if date_to is not None:
        query = query.where(CashSession.business_date <= date_to)
    if pos_id is not None:
        query = query.where(CashSession.pos_id == pos_id)
    sessions = (await db.execute(query.order_by(CashSession.closed_at.desc()).limit(limit))).scalars().all()

    tills = await _tills(db, company_id, active_only=False)
    names = await _user_names(db, [s.opened_by_user_id for s in sessions] + [s.closed_by_user_id for s in sessions])
    return [{
        "session_id": s.id, "pos_id": s.pos_id,
        "pos_name": tills[s.pos_id][0].name if s.pos_id in tills else "-",
        "activity_name": tills[s.pos_id][1] if s.pos_id in tills else "-",
        "business_date": s.business_date,
        "opened_at": s.opened_at, "opened_by": names.get(s.opened_by_user_id),
        "closed_at": s.closed_at, "closed_by": names.get(s.closed_by_user_id),
        "opening_amount": _money(s.opening_amount), "expected": _money(s.closing_amount_expected),
        "counted": _money(s.closing_amount_counted), "difference": _money(s.closing_difference),
        "notes": s.closing_notes,
    } for s in sessions]
