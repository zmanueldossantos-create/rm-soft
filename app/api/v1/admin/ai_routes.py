"""
The AI assistant's platform settings (SUPER_ADMIN): the provider, model, key and message limit, the connection test,
and each company's switches. The company's own confirmations are in app/api/v1/ai/routes.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai_settings import (
    AiTestResponse, CompanyAiResponse, CompanyAiSwitchesRequest, PlatformAiResponse, PlatformAiUpdateRequest,
    TelegramBotResponse, TelegramTokenRequest, WhatsAppSettingsRequest, WhatsAppSettingsResponse,
)
from app.services.ai import whatsapp
from app.services.ai.telegram import TelegramError, set_bot_token
from app.services.ai_settings_service import (
    AiSettingsError, get_company_ai, get_platform_ai, test_platform_ai, update_company_ai_switches, update_platform_ai,
)

router = APIRouter(prefix="/api/v1", tags=["admin"])


def _refused(e: AiSettingsError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/admin/ai-settings", response_model=PlatformAiResponse)
async def read_platform_ai(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await get_platform_ai(db)


@router.put("/admin/ai-settings", response_model=PlatformAiResponse)
async def write_platform_ai(payload: PlatformAiUpdateRequest, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await update_platform_ai(db, payload.provider, payload.model, payload.api_key, payload.monthly_limit)
    except AiSettingsError as e:
        raise _refused(e)


@router.post("/admin/ai-settings/test", response_model=AiTestResponse)
async def check_platform_ai(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await test_platform_ai(db)
    except AiSettingsError as e:
        raise _refused(e)


@router.get("/admin/companies/{company_id}/ai-settings", response_model=CompanyAiResponse)
async def read_company_ai_admin(company_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await get_company_ai(db, company_id)
    except AiSettingsError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/admin/companies/{company_id}/ai-settings", response_model=CompanyAiResponse)
async def write_company_ai_admin(company_id: uuid.UUID, payload: CompanyAiSwitchesRequest,
                                 db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await update_company_ai_switches(db, company_id, payload.ai_enabled, payload.whatsapp_enabled,
                                                payload.telegram_enabled, payload.email_enabled, payload.monthly_limit)
    except AiSettingsError as e:
        raise _refused(e)


@router.put("/admin/ai-settings/telegram", response_model=TelegramBotResponse)
async def write_telegram_bot(payload: TelegramTokenRequest, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """The bot's token, checked with Telegram and kept encrypted ("" removes the bot)."""
    try:
        return await set_bot_token(db, payload.token)
    except TelegramError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/admin/ai-settings/whatsapp", response_model=WhatsAppSettingsResponse)
async def read_whatsapp(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await whatsapp.get_settings_view(db)


@router.put("/admin/ai-settings/whatsapp", response_model=WhatsAppSettingsResponse)
async def write_whatsapp(payload: WhatsAppSettingsRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """The RM SOFT number on WhatsApp Cloud API: Meta's number id, the token and the app secret (kept encrypted)."""
    return await whatsapp.update_settings(db, payload.phone_number_id, payload.display_number, payload.access_token,
                                          payload.app_secret)
