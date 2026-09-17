"""
Read access to the Denomination catalog (platform-wide, SUPER_ADMIN managed -
see model docstring). Companies only ever list denominations to build the
Moedeiro counting grid, never create/edit them.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.denomination import Denomination


async def list_denominations(db: AsyncSession, currency_id: uuid.UUID | None = None) -> list[Denomination]:
    query = select(Denomination).where(Denomination.is_active.is_(True))
    if currency_id is not None:
        query = query.where(Denomination.currency_id == currency_id)
    query = query.order_by(Denomination.denomination_type, Denomination.value.desc())
    result = await db.execute(query)
    return list(result.scalars().all())
