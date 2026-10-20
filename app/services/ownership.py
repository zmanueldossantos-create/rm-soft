"""
Isolation between client companies: an object named in a request (a customer, an activity, a service...) must belong
to the company of the user who sends it. Every query of a company's data is filtered by its company_id; this is the
same rule for the ids a form refers to - another company's object is "not found", never used.
"""
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class NotOwnedError(Exception):
    """An id that is not one of the company's objects - answered 404 with its message (app.main)."""


async def ensure_owned(db: AsyncSession, company_id: uuid.UUID, model, object_id: uuid.UUID | None, message: str) -> None:
    """Raises NotOwnedError(message) unless object_id is None or one of the company's rows of model."""
    if object_id is None:
        return
    found = (await db.execute(select(model.id).where(model.id == object_id, model.company_id == company_id))).scalar_one_or_none()
    if found is None:
        raise NotOwnedError(message)
