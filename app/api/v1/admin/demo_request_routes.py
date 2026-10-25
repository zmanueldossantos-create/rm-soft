"""«Pedidos» (SUPER_ADMIN): the demonstration requests of the public site, and their follow-up."""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_role
from app.core.config import get_settings
from app.core.database import get_db
from app.models.user import User
from app.schemas.demo_request import DemoRequestUpdate
from app.services.demo_request_service import demo_requests_summary, list_demo_requests, update_demo_request

router = APIRouter(prefix="/api/v1/admin/demo-requests", tags=["admin"])


@router.get("/summary")
async def get_summary(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """How many requests in each state - the menu's badge. enabled: this server runs the public site (PUBLIC_SITE);
    on a client's server the menu entry is not shown."""
    return {"enabled": get_settings().PUBLIC_SITE, "counts": await demo_requests_summary(db)}


@router.get("")
async def get_requests(status_filter: str | None = None, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await list_demo_requests(db, status_filter)


@router.patch("/{request_id}")
async def patch_request(request_id: uuid.UUID, payload: DemoRequestUpdate, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await update_demo_request(db, request_id, payload.status, payload.notes, current_user.id)
    except LookupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
