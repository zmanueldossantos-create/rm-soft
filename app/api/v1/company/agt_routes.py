"""Definições da Empresa → Faturação Eletrónica (the gestor: company:manage): the taxpayer's key issued by the AGT, the
connection test and the journal of the calls to the AGT."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.agt_call import AgtCall
from app.models.company import Company
from app.models.user import User
from app.services import agt_client, agt_settings_service
from app.services.agt_signing import AgtKeyError

router = APIRouter(prefix="/api/v1/company/me/agt", tags=["agt"])


class KeyRequest(BaseModel):
    private_key: str = Field(default="", max_length=10000)


async def _company(db: AsyncSession, user: User) -> Company:
    company = await db.get(Company, user.company_id)
    if company is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")
    return company


@router.get("")
async def read(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("company:manage"))):
    return await agt_settings_service.company_view(db, await _company(db, current_user))


@router.put("/key")
async def save_key(payload: KeyRequest, db: AsyncSession = Depends(get_db),
                   current_user: User = Depends(require_permission("company:manage"))):
    """The private key from the taxpayer's portal (PEM): kept encrypted, never sent back. Empty: removed."""
    try:
        return await agt_settings_service.save_company_key(db, await _company(db, current_user), payload.private_key)
    except AgtKeyError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


class TestNifRequest(BaseModel):
    nif: str | None = None


@router.put("/test-nif")
async def save_test_nif(payload: TestNifRequest, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("company:manage"))):
    """Homologação: send as one of the AGT's test NIFs (null: as this company's own NIF)."""
    try:
        return await agt_settings_service.save_company_test_nif(db, await _company(db, current_user), payload.nif)
    except agt_settings_service.AgtSettingsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/test")
async def test(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("company:manage"))):
    """listarSeries for this company: the AGT's answer as it came (or why it could not be reached)."""
    try:
        return await agt_client.test_connection(db, await _company(db, current_user))
    except agt_client.AgtConfigError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/calls")
async def calls(limit: int = 30, db: AsyncSession = Depends(get_db),
                current_user: User = Depends(require_permission("company:manage"))):
    """The last calls to the AGT (the journal, 90 days) - what was sent and what the AGT answered."""
    rows = (await db.execute(select(AgtCall).where(AgtCall.company_id == current_user.company_id)
                             .order_by(AgtCall.created_at.desc()).limit(max(1, min(limit, 100))))).scalars().all()
    return [{"id": str(c.id), "service": c.service, "environment": c.environment, "status_code": c.status_code,
             "error": c.error, "duration_ms": c.duration_ms, "created_at": c.created_at.isoformat(),
             "request": c.request_body, "response": c.response_body} for c in rows]
