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
    from app.core.config import get_settings
    from app.services import relay_agent
    settings = get_settings()
    return {"allowed": True, "scopes": [{"code": c, "label": label} for c, label in keys.SCOPES.items()],
            "rate_per_minute": keys.RATE_PER_MINUTE, "journal_days": keys.JOURNAL_DAYS,
            "keys": await keys.list_keys(db, current_user.company_id),
            # the client's server (local installation): its link to the platform's relay - None elsewhere
            "relay": await relay_agent.view(db, current_user.company_id) if settings.is_local else None}


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


# ------------------------------------------------------------------------------- the link to the relay (local only)

class RelayRequest(BaseModel):
    relay_url: str = Field(max_length=300)
    secret: str | None = Field(default=None, max_length=200)
    is_active: bool = True


async def _local_only(db: AsyncSession, current_user: User) -> None:
    from app.core.config import get_settings
    settings = get_settings()
    if not settings.is_local:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Só numa instalação local")
    await require_option(db, current_user.company_id, keys.OPTION)


@router.put("/relay")
async def save_relay(payload: RelayRequest, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_permission("company:manage"))):
    """The platform's address and the relay's secret (given by RM SOFT). The secret is never shown again."""
    from app.services import relay_agent
    await _local_only(db, current_user)
    try:
        return await relay_agent.save(db, current_user.company_id, payload.relay_url, payload.secret, payload.is_active)
    except relay_agent.RelayAgentError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/relay/test")
async def test_relay(db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_permission("company:manage"))):
    from app.services import relay_agent
    await _local_only(db, current_user)
    try:
        return await relay_agent.test_connection(db, current_user.company_id)
    except relay_agent.RelayAgentError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/relay")
async def remove_relay(db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("company:manage"))):
    from app.services import relay_agent
    await _local_only(db, current_user)
    return await relay_agent.remove(db, current_user.company_id)
