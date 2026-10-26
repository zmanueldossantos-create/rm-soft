"""Definições da Empresa → Notificações (the gestor: company:manage; option NOTIFICACOES of the plan)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.services import notification_service as notifications
from app.services.plan_service import has_option, require_option

router = APIRouter(prefix="/api/v1/company/me/notifications", tags=["notifications"])


class SettingsRequest(BaseModel):
    enabled: bool = True
    include_gestor_actions: bool = False
    sale_min_amount: float | None = None


class RecipientRequest(BaseModel):
    name: str = Field(default="", max_length=200)
    channel: str | None = None
    address: str | None = Field(default=None, max_length=200)
    events: list[str] = []
    is_active: bool = True


def _refused(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("")
async def read(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("company:manage"))):
    """allowed false: the plan has no Notificações (the tab is not shown)."""
    if not await has_option(db, current_user.company_id, notifications.OPTION):
        return {"allowed": False}
    return {"allowed": True, **await notifications.overview(db, current_user.company_id)}


@router.put("/settings")
async def write_settings(payload: SettingsRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, notifications.OPTION)
    try:
        await notifications.update_settings(db, current_user.company_id, payload.enabled, payload.include_gestor_actions,
                                            payload.sale_min_amount)
    except notifications.NotificationError as e:
        raise _refused(e)
    return {"ok": True}


@router.post("/recipients", status_code=status.HTTP_201_CREATED)
async def create_recipient(payload: RecipientRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, notifications.OPTION)
    try:
        return await notifications.add_recipient(db, current_user.company_id, payload.model_dump())
    except notifications.NotificationError as e:
        raise _refused(e)


@router.put("/recipients/{recipient_id}")
async def edit_recipient(recipient_id: uuid.UUID, payload: RecipientRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, notifications.OPTION)
    try:
        return await notifications.update_recipient(db, current_user.company_id, recipient_id, payload.model_dump())
    except (notifications.NotificationError, LookupError) as e:
        raise _refused(e)


@router.delete("/recipients/{recipient_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_recipient(recipient_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("company:manage"))):
    try:
        await notifications.delete_recipient(db, current_user.company_id, recipient_id)
    except LookupError as e:
        raise _refused(e)


@router.post("/recipients/{recipient_id}/test")
async def test_recipient(recipient_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, notifications.OPTION)
    try:
        await notifications.send_test(db, current_user.company_id, recipient_id)
    except (notifications.NotificationError, LookupError) as e:
        raise _refused(e)
    return {"ok": True}
