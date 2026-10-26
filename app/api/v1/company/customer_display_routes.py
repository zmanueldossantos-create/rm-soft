"""Ecrã do cliente (option ECRA_CLIENTE): the till reads its activity's screen (pos:checkout); the gestor sets it in
Configurações → Atividades (company:manage)."""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.services import customer_display_service as display
from app.services.plan_service import has_option, require_option

router = APIRouter(prefix="/api/v1/customer-display", tags=["customer-display"])


class SettingsRequest(BaseModel):
    welcome_message: str | None = Field(default=None, max_length=200)
    slide_seconds: int = display.DEFAULT_SLIDE_SECONDS


def _refused(e: Exception) -> HTTPException:
    if isinstance(e, LookupError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/{activity_id}")
async def read(activity_id: uuid.UUID, db: AsyncSession = Depends(get_db),
               current_user: User = Depends(require_permission("pos:checkout"))):
    """allowed false: the plan has no Ecrã do cliente (the Caixa shows no button, Atividades no block)."""
    if not await has_option(db, current_user.company_id, display.OPTION):
        return {"allowed": False}
    try:
        return {"allowed": True, **await display.read(db, current_user.company_id, activity_id)}
    except LookupError as e:
        raise _refused(e)


@router.put("/{activity_id}")
async def write_settings(activity_id: uuid.UUID, payload: SettingsRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, display.OPTION)
    try:
        return await display.update_settings(db, current_user.company_id, activity_id, payload.welcome_message,
                                             payload.slide_seconds)
    except (display.CustomerDisplayError, LookupError) as e:
        raise _refused(e)


@router.post("/{activity_id}/images", status_code=status.HTTP_201_CREATED)
async def add_image(activity_id: uuid.UUID, file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, display.OPTION)
    contents = await file.read(display.MAX_IMAGE_BYTES + 1)
    try:
        return await display.add_image(db, current_user.company_id, activity_id, file.filename, contents)
    except (display.CustomerDisplayError, LookupError) as e:
        raise _refused(e)


@router.delete("/images/{image_id}")
async def delete_image(image_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("company:manage"))):
    await require_option(db, current_user.company_id, display.OPTION)
    try:
        return await display.delete_image(db, current_user.company_id, image_id)
    except LookupError as e:
        raise _refused(e)
