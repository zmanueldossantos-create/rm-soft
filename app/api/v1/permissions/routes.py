from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role, get_current_user
from app.models.user import User
from app.schemas.permission import PermissionMatrixEntry, SetRolePermissionRequest
from app.services.permission_service import get_permission_matrix, set_role_permission, list_my_permissions

router = APIRouter(prefix="/api/v1/permissions", tags=["permissions"])

# Configuring who-can-do-what is a GESTOR-only action, same as any other
# catalog/config screen - not itself migrated to require_permission (this
# IS the admin screen that manages the dynamic system, so it stays on the
# older, simpler require_role check to avoid a chicken-and-egg dependency).


@router.get("/matrix", response_model=list[PermissionMatrixEntry])
async def get_matrix(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    return await get_permission_matrix(db, current_user.company_id)


@router.post("/matrix")
async def post_set_permission(
    payload: SetRolePermissionRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("GESTOR")),
):
    await set_role_permission(db, current_user.company_id, payload.role, payload.permission_id, payload.granted)
    return {"ok": True}


@router.get("/mine", response_model=list[str])
async def get_my_permissions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Any authenticated user's own granted permission codes - lets the
    frontend show/hide dynamic-permission-gated buttons without needing
    GESTOR-only access to the full matrix."""
    if current_user.company_id is None:
        return []
    return await list_my_permissions(db, current_user.company_id, current_user.role.value)
