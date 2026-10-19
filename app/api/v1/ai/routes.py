"""
The AI assistant of the signed-in user's company: what the platform switched on and the gestor's confirmations. The
platform settings (SUPER_ADMIN) are in app/api/v1/admin/ai_routes.py.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.schemas.ai_settings import CompanyAiConfirmationsRequest, CompanyAiResponse
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
