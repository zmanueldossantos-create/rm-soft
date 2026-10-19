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
from app.schemas.ai_settings import (
    AiConversationResponse, AiMessageResponse, AskRequest, AskResponse, AssistantStatusResponse,
    CompanyAiConfirmationsRequest, CompanyAiResponse,
)
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


@router.get("/ai/conversations/{conversation_id}/messages", response_model=list[AiMessageResponse])
async def read_conversation_messages(conversation_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_permission("assistant:use"))):
    try:
        return await list_messages(db, current_user.company_id, current_user.id, conversation_id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.post("/ai/ask", response_model=AskResponse)
async def ask_assistant(payload: AskRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("assistant:use"))):
    try:
        conversation, message = await ask(db, current_user, payload.message, payload.conversation_id)
    except ConversationNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except AssistantError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    counter = await assistant_status(db, current_user.company_id)
    return {"conversation": conversation, "message": message, "used": counter["used"], "limit": counter["limit"]}
