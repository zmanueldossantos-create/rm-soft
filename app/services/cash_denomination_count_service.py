"""
Business logic for cash-drawer denomination counting (Moedeiro / billetage).
Only meaningful when the session's POS has billetage_enabled=True - see
Denomination/CashDenominationCount model docstrings.
"""
import uuid
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.cash_denomination_count import CashDenominationCount, CashDenominationCountLine, DenominationCountType
from app.models.denomination import Denomination


class EmptyCountError(Exception):
    pass


class DenominationNotFoundError(Exception):
    pass


async def record_denomination_count(
    db: AsyncSession,
    company_id: uuid.UUID,
    cash_session_id: uuid.UUID,
    count_type: DenominationCountType,
    counted_by_user_id: uuid.UUID,
    lines: list[dict],  # [{"denomination_id": ..., "quantity": ...}, ...]
) -> tuple[CashDenominationCount, float]:
    """Records a count and returns (count, total_amount) - total is quantity x denomination.value summed."""
    if not lines:
        raise EmptyCountError("O contagem de billetagem nao pode estar vazia")

    denomination_ids = [line["denomination_id"] for line in lines]
    result = await db.execute(select(Denomination).where(Denomination.id.in_(denomination_ids)))
    denominations_by_id = {d.id: d for d in result.scalars().all()}

    total = 0.0
    count = CashDenominationCount(
        company_id=company_id, cash_session_id=cash_session_id,
        count_type=count_type, counted_by_user_id=counted_by_user_id,
    )
    db.add(count)
    await db.flush()

    for line in lines:
        denomination = denominations_by_id.get(line["denomination_id"])
        if denomination is None:
            raise DenominationNotFoundError("Uma das denominacoes indicadas nao foi encontrada")
        quantity = int(line["quantity"])
        if quantity <= 0:
            continue
        db.add(CashDenominationCountLine(count_id=count.id, denomination_id=denomination.id, quantity=quantity))
        total += quantity * float(denomination.value)

    await db.commit()
    await db.refresh(count)
    return count, round(total, 2)


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
