"""
The AI assistant of the signed-in user's company: what the platform switched on, the gestor's confirmations, and the
assistant itself (its status, the user's conversations, a question). The platform settings (SUPER_ADMIN) are in
app/api/v1/admin/ai_routes.py.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from sqlalchemy import select

from app.models.ai_pending_action import AiPendingAction
from app.schemas.ai_settings import (
    ActionDecisionResponse, AiConversationResponse, AiMessageResponse, AskRequest, AskResponse, AssistantStatusResponse, AiActionResponse,
    CompanyAiConfirmationsRequest, CompanyAiResponse, EmailSettingsRequest, EmailSettingsResponse, EmailTestRequest,
)
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
