"""
Contingência (Faturação Eletrónica): whether this company's new documents take the C series because the AGT cannot be
reached. The state itself (automatic after repeated network failures, the gestor's switch, the return to N) comes
with step D of the AGT work; until then a company is never in contingência.
"""
import uuid

from sqlalchemy.ext.asyncio import AsyncSession


async def in_contingency(db: AsyncSession, company_id: uuid.UUID) -> bool:
    return False
