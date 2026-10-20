"""
Ajuda: the user guides this user may read (app.services.help_guides) - the circuits and the screens his role opens.
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services.help_guides import visible_guides
from app.services.permission_service import list_my_permissions

router = APIRouter(prefix="/api/v1/help", tags=["help"])


@router.get("/guides")
async def get_guides(db: AsyncSession = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The guides of the user's screens, filtered with the same permissions as the menu."""
    if current_user.company_id is None:  # the platform (SUPER_ADMIN): its own guides
        return visible_guides(set(), current_user.role.value)
    permissions = set(await list_my_permissions(db, current_user.company_id, current_user.role.value))
    return visible_guides(permissions, current_user.role.value)
