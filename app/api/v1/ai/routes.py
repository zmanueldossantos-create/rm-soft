"""
The AI assistant of the signed-in user's company: what the platform switched on, the gestor's confirmations, and the
assistant itself (its status, the user's conversations, a question). The platform settings (SUPER_ADMIN) are in
app/api/v1/admin/ai_routes.py.
"""
import json
import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from sqlalchemy import select

from app.models.ai_pending_action import AiPendingAction
from app.schemas.ai_settings import (
    ActionDecisionResponse, AiConversationResponse, AiMessageResponse, AskRequest, AskResponse, AssistantStatusResponse, AiActionResponse,
    ChannelsResponse, CompanyAiConfirmationsRequest, CompanyAiResponse, EmailSettingsRequest, EmailSettingsResponse,
    EmailTestRequest, LinkCodeResponse,
)
from app.services.ai.channels import CHANNELS, ChannelError, create_link_code, list_links, unlink
from app.services.platform_settings_service import get_or_create_platform_settings
from app.services.ai.actions import ActionError, decide_action
from app.services.email_service import EmailError, get_email_settings, send_test_email, update_email_settings
from app.services.ai.assistant_service import (
    AssistantError, ConversationNotFoundError, ask, assistant_status, list_conversations, list_messages,
)
from app.services.ai_settings_service import get_company_ai, update_company_ai_confirmations

router = APIRouter(prefix="/api/v1", tags=["ai"])


@router.get("/company/me/ai-settings", response_model=CompanyAiResponse)
async def read_my_company_ai(db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("company:view"))):
    return await get_company_ai(db, current_user.company_id)


@router.put("/company/me/ai-settings", response_model=CompanyAiResponse)
async def write_my_company_ai(payload: CompanyAiConfirmationsRequest, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("company:manage"))):
    return await update_company_ai_confirmations(db, current_user.company_id, payload.confirm_documents,
                                                 payload.confirm_sends)


# ---------- The assistant itself (permission assistant:use - the GESTOR by default)


@router.get("/ai/status", response_model=AssistantStatusResponse)
async def read_assistant_status(db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("assistant:use"))):
    return await assistant_status(db, current_user.company_id)


@router.get("/ai/conversations", response_model=list[AiConversationResponse])
async def read_conversations(db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("assistant:use"))):
    return await list_conversations(db, current_user.company_id, current_user.id)


async def _with_actions(db: AsyncSession, messages) -> list[dict]:
    """The messages with the card of the action each one prepared."""
    ids = [m.action_id for m in messages if m.action_id]
    actions = {a.id: a for a in (await db.execute(select(AiPendingAction).where(AiPendingAction.id.in_(ids)))).scalars().all()} if ids else {}
    out = []
    for m in messages:
        item = AiMessageResponse.model_validate(m).model_dump()
        action = actions.get(m.action_id)
        item["action"] = AiActionResponse.model_validate(action).model_dump() if action else None
        out.append(item)
    return out


@router.get("/ai/conversations/{conversation_id}/messages", response_model=list[AiMessageResponse])
async def read_conversation_messages(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("assistant:use"))):
    try:
        return await _with_actions(db, await list_messages(db, current_user.company_id, current_user.id, conversation_id))
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/ai/ask", response_model=AskResponse)
async def ask_assistant(payload: AskRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("assistant:use"))):
    company_id = current_user.company_id  # kept: a refused action rolls the session back
    try:
        conversation, message = await ask(db, current_user, payload.message, payload.conversation_id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AssistantError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    counter = await assistant_status(db, company_id)
    return {"conversation": conversation, "message": (await _with_actions(db, [message]))[0],
            "used": counter["used"], "limit": counter["limit"]}


@router.post("/ai/actions/{action_id}/{decision}", response_model=ActionDecisionResponse)
async def decide_assistant_action(action_id: uuid.UUID, decision: str, db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(require_permission("assistant:use"))):
    """Confirmar (confirm) or Cancelar (cancel) an action the assistant prepared - only by the user it was prepared for."""
    if decision not in ("confirm", "cancel"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decisão desconhecida")
    try:
        action, text = await decide_action(db, current_user.company_id, current_user.id, action_id, decision == "confirm")
    except ActionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return {"action": action, "message": text}


# ---------- The company's email account (company:manage)

@router.get("/company/me/email-settings", response_model=EmailSettingsResponse)
async def read_email_settings(db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("company:view"))):
    return await get_email_settings(db, current_user.company_id)


@router.put("/company/me/email-settings", response_model=EmailSettingsResponse)
async def write_email_settings(payload: EmailSettingsRequest, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_permission("company:manage"))):
    try:
        return await update_email_settings(db, current_user.company_id, payload.smtp_host, payload.smtp_port,
                                           payload.security, payload.username, payload.password, payload.from_email,
                                           payload.from_name, payload.is_active)
    except EmailError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/company/me/email-settings/test")
async def test_email_settings(payload: EmailTestRequest, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("company:manage"))):
    try:
        await send_test_email(db, current_user.company_id, payload.to)
    except EmailError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return {"sent_to": payload.to}



# ---------- The assistant on WhatsApp / Telegram (the user's own chats)

@router.get("/ai/channels", response_model=ChannelsResponse)
async def read_my_channels(db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("assistant:use"))):
    platform = await get_or_create_platform_settings(db)
    from app.services.ai.whatsapp import settings_view
    wa = settings_view(platform)
    return {"channels": await list_links(db, current_user.company_id, current_user.id),
            "telegram_bot_username": platform.telegram_bot_username if platform.telegram_bot_token_encrypted else None,
            "whatsapp_configured": wa["configured"], "whatsapp_number": wa["display_number"] if wa["configured"] else None}


@router.post("/ai/channels/{channel}/code", response_model=LinkCodeResponse)
async def new_link_code(channel: str, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("assistant:use"))):
    channel = channel.upper()
    platform = await get_or_create_platform_settings(db)
    if channel == "TELEGRAM" and not platform.telegram_bot_token_encrypted:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O bot do Telegram ainda não está configurado na plataforma")
    if channel == "WHATSAPP":
        from app.services.ai.whatsapp import settings_view
        if not settings_view(platform)["configured"]:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="O WhatsApp ainda não está configurado na plataforma")
    try:
        code = await create_link_code(db, current_user.company_id, current_user.id, channel)
    except ChannelError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    link = None
    if channel == "TELEGRAM" and platform.telegram_bot_username:
        link = f"https://t.me/{platform.telegram_bot_username}?start={code['code']}"
    elif channel == "WHATSAPP" and platform.whatsapp_display_number:  # opens WhatsApp with «LIGAR 123456» typed
        link = f"https://wa.me/{platform.whatsapp_display_number.lstrip('+')}?text=LIGAR%20{code['code']}"
    return {**code, "link": link}


@router.post("/ai/channels/{channel}/unlink", status_code=status.HTTP_204_NO_CONTENT)
async def unlink_my_channel(channel: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("assistant:use"))):
    if channel.upper() not in CHANNELS:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Canal desconhecido")
    await unlink(db, current_user.company_id, current_user.id, channel.upper())


@router.post("/channels/telegram/webhook", include_in_schema=False)
async def telegram_webhook(update: dict, background: BackgroundTasks, db: AsyncSession = Depends(get_db),
                           x_telegram_bot_api_secret_token: str | None = Header(default=None)):
    """SaaS: Telegram calls here (the secret set with the webhook proves it). Answered at once, handled after."""
    from app.services.ai.telegram import process_update
    platform = await get_or_create_platform_settings(db)
    if not platform.telegram_webhook_secret or x_telegram_bot_api_secret_token != platform.telegram_webhook_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    background.add_task(process_update, update)
    return {"ok": True}



@router.get("/channels/whatsapp/webhook", include_in_schema=False)
async def whatsapp_verify(request: Request, db: AsyncSession = Depends(get_db)):
    """Meta registering the webhook: answers its challenge when our verify token is given."""
    from app.services.ai.whatsapp import verify_subscription
    params = request.query_params
    challenge = verify_subscription(await get_or_create_platform_settings(db), params.get("hub.mode"),
                                    params.get("hub.verify_token"), params.get("hub.challenge"))
    if challenge is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    return Response(content=challenge, media_type="text/plain")


@router.post("/channels/whatsapp/webhook", include_in_schema=False)
async def whatsapp_webhook(request: Request, background: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    """Meta's calls, signed with the app secret: answered at once, each message handled after."""
    from app.services.ai.whatsapp import incoming_messages, process_message, signature_valid
    body = await request.body()
    if not signature_valid(await get_or_create_platform_settings(db), body, request.headers.get("x-hub-signature-256")):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Forbidden")
    for message in incoming_messages(json.loads(body or b"{}")):
        background.add_task(process_message, message)
    return {"ok": True}
