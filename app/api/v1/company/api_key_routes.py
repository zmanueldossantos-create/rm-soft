"""Configurações → Integração API (the gestor: company:manage; option INTEGRACAO_API): the access keys of the public
API and its journal."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.services import api_key_service as keys
from app.services.plan_service import has_option, require_option

router = APIRouter(prefix="/api/v1/company/me/api-keys", tags=["api-keys"])


class KeyRequest(BaseModel):
    name: str = Field(default="", max_length=100)
    scopes: list[str] = []


@router.get("")
async def read(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("company:manage"))):
    """allowed false: the plan has no Integração API (the tab is not shown)."""
    if not await has_option(db, current_user.company_id, keys.OPTION):
        return {"allowed": False}
    return {"allowed": True, "scopes": [{"code": c, "label": label} for c, label in keys.SCOPES.items()],
            "rate_per_minute": keys.RATE_PER_MINUTE, "journal_days": keys.JOURNAL_DAYS,
            "keys": await keys.list_keys(db, current_user.company_id)}


@router.post("", status_code=status.HTTP_201_CREATED)
async def create(payload: KeyRequest, db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(require_permission("company:manage"))):
    """The answer holds «key»: the only time the whole key is given."""
    await require_option(db, current_user.company_id, keys.OPTION)
    try:
        return await keys.create_key(db, current_user.company_id, current_user.id, payload.name, payload.scopes)
    except keys.ApiKeyError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/{key_id}")
async def revoke(key_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                 current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, keys.OPTION)
    try:
        return await keys.revoke_key(db, current_user.company_id, key_id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/journal")
async def journal(key_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db),
                  current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, keys.OPTION)
    return await keys.read_journal(db, current_user.company_id, key_id)
