"""
Business logic for cash-drawer denomination counting (Moedeiro / billetage).
Only meaningful when the session's POS has billetage_enabled=True - see
Denomination/CashDenominationCount model docstrings.
"""
import uuid
from datetime import date

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_denomination_count import CashDenominationCount, CashDenominationCountLine, DenominationCountType
from app.models.cash_session import CashSession, CashSessionStatus
from app.models.denomination import Denomination


class EmptyCountError(Exception):
    pass


class DenominationNotFoundError(Exception):
    pass


class CountSessionNotFoundError(Exception):
    """The session of a count must be one of the company's, still open: a count is a fact of the drawer in use."""


class CountTotalMismatchError(Exception):
    """The notes and coins of a transfer must add up to its amount."""


async def record_denomination_count(
    db: AsyncSession,
    company_id: uuid.UUID,
    cash_session_id: uuid.UUID,
    count_type: DenominationCountType,
    counted_by_user_id: uuid.UUID,
    lines: list[dict],  # [{"denomination_id": ..., "quantity": ...}, ...]
    cash_movement_id: uuid.UUID | None = None,
    expected_total: float | None = None,
) -> tuple[CashDenominationCount, float]:
    """Records a count and returns (count, total_amount) - total is quantity x denomination.value summed.
    cash_movement_id: the transfer of a TRANSF_SAIDA / TRANSF_ENTRADA count. expected_total: the amount the count must
    reach (a transfer's), checked before anything is written. Commits - with whatever the caller added before."""
    session = (await db.execute(
        select(CashSession).where(CashSession.id == cash_session_id, CashSession.company_id == company_id)
    )).scalar_one_or_none()
    if session is None or session.status != CashSessionStatus.ABERTA:
        raise CountSessionNotFoundError("Sessão de caixa não encontrada ou já fechada")

    denomination_ids = [line["denomination_id"] for line in lines]
    result = await db.execute(select(Denomination).where(Denomination.id.in_(denomination_ids)))
    denominations_by_id = {d.id: d for d in result.scalars().all()}

    # every line checked and the total known before writing anything
    kept: list[tuple[Denomination, int]] = []
    for line in lines:
        denomination = denominations_by_id.get(line["denomination_id"])
        if denomination is None:
            raise DenominationNotFoundError("Uma das denominações indicadas não foi encontrada")
        quantity = int(line["quantity"])
        if quantity > 0:
            kept.append((denomination, quantity))
    if not kept:
        raise EmptyCountError("A contagem de billetagem não pode estar vazia")
    total = round(sum(quantity * float(denomination.value) for denomination, quantity in kept), 2)
    if expected_total is not None and abs(total - float(expected_total)) >= 0.01:
        raise CountTotalMismatchError(
            f"As notas e moedas somam {total:,.2f} Kz - devem somar {float(expected_total):,.2f} Kz".replace(",", " ")
        )

    count = CashDenominationCount(
        company_id=company_id, cash_session_id=cash_session_id, count_type=count_type,
        counted_by_user_id=counted_by_user_id, cash_movement_id=cash_movement_id,
    )
    db.add(count)
    await db.flush()
    for denomination, quantity in kept:
        db.add(CashDenominationCountLine(count_id=count.id, denomination_id=denomination.id, quantity=quantity))

    await db.commit()
    await db.refresh(count)
    return count, total


async def get_latest_count(
    db: AsyncSession, company_id: uuid.UUID, cash_session_id: uuid.UUID, count_type: DenominationCountType,
) -> CashDenominationCount | None:
    result = await db.execute(
        select(CashDenominationCount).where(
            CashDenominationCount.company_id == company_id,
            CashDenominationCount.cash_session_id == cash_session_id,
            CashDenominationCount.count_type == count_type,
        ).order_by(CashDenominationCount.counted_at.desc())
    )
    return result.scalars().first()


async def get_count_total(db: AsyncSession, count_id: uuid.UUID) -> float:
    """Sums quantity x denomination.value for a given count's lines."""
    result = await db.execute(
        select(CashDenominationCountLine, Denomination)
        .join(Denomination, Denomination.id == CashDenominationCountLine.denomination_id)
        .where(CashDenominationCountLine.count_id == count_id)
    )
    total = 0.0
    for line, denomination in result.all():
        total += line.quantity * float(denomination.value)
    return round(total, 2)


async def get_count_lines(db: AsyncSession, count_id: uuid.UUID) -> list[CashDenominationCountLine]:
    result = await db.execute(select(CashDenominationCountLine).where(CashDenominationCountLine.count_id == count_id))
    return list(result.scalars().all())



async def get_count_breakdown(db: AsyncSession, count_id: uuid.UUID) -> list[dict]:
    """The notes and coins of a count, highest value first - the billetage table of the closing report."""
    rows = (await db.execute(
        select(CashDenominationCountLine.quantity, Denomination.value, Denomination.denomination_type)
        .join(Denomination, Denomination.id == CashDenominationCountLine.denomination_id)
        .where(CashDenominationCountLine.count_id == count_id)
        .order_by(Denomination.value.desc(), Denomination.denomination_type)
    )).all()
    return [{"value": float(value), "type": getattr(kind, "value", kind), "quantity": int(quantity),
             "amount": round(int(quantity) * float(value), 2)} for quantity, value, kind in rows]


async def get_movement_count(
    db: AsyncSession, company_id: uuid.UUID, cash_movement_id: uuid.UUID, count_type: DenominationCountType,
) -> CashDenominationCount | None:
    """The notes and coins of one side of a transfer (TRANSF_SAIDA: sent, TRANSF_ENTRADA: received)."""
    return (await db.execute(
        select(CashDenominationCount).where(
            CashDenominationCount.company_id == company_id,
            CashDenominationCount.cash_movement_id == cash_movement_id,
            CashDenominationCount.count_type == count_type,
        ).order_by(CashDenominationCount.counted_at.desc())
    )).scalars().first()


async def delete_movement_counts(db: AsyncSession, cash_movement_id: uuid.UUID) -> None:
    """A cancelled transfer takes its notes and coins with it (no commit - the caller's). Plain deletes, lines first:
    the two tables have no ORM relationship to order them."""
    count_ids = select(CashDenominationCount.id).where(CashDenominationCount.cash_movement_id == cash_movement_id)
    await db.execute(delete(CashDenominationCountLine).where(CashDenominationCountLine.count_id.in_(count_ids)))
    await db.execute(delete(CashDenominationCount).where(CashDenominationCount.cash_movement_id == cash_movement_id))
