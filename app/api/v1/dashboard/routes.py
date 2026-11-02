"""
Dashboard summary route - available to all company-scoped roles.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/api/v1/dashboard", tags=["dashboard"])


@router.get("/summary")
async def summary(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("dashboard:view")),
):
    """Returns aggregated stats for the company's dashboard - each block only for who may see it."""
    from app.services.permission_service import list_my_permissions
    role = current_user.role.value if hasattr(current_user.role, "value") else current_user.role
    permissions = set(await list_my_permissions(db, current_user.company_id, role))
    return await get_dashboard_summary(db, current_user.company_id, permissions)
