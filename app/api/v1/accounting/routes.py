"""
Routes of the Contabilidade module (capability ACCOUNTING): the chart of accounts - see
app.services.chart_of_accounts_service.
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_permission
from app.core.database import get_db
from app.models.user import User
from app.services.chart_of_accounts_service import (
    AccountNotFoundError, ChartError, ChartImportError, create_account, delete_account, excel_template, get_chart,
    import_chart, start_chart, update_account,
)

router = APIRouter(prefix="/api/v1/accounting", tags=["accounting"])
MAX_UPLOAD = 5 * 1024 * 1024


class ChartStartRequest(BaseModel):
    source: str  # PGC, PROPRIO or VAZIO


class AccountCreateRequest(BaseModel):
    code: str
    name: str


class AccountUpdateRequest(BaseModel):
    name: str
    is_active: bool = True


def _account(a) -> dict:
    return {"id": a.id, "code": a.code, "name": a.name, "parent_id": a.parent_id, "level": a.level,
            "is_active": a.is_active}


@router.get("/chart")
async def get_chart_of_accounts(db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("accounting:chart_view"))):
    return await get_chart(db, current_user.company_id)


@router.post("/chart/start")
async def post_chart_start(payload: ChartStartRequest, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        return await start_chart(db, current_user.company_id, payload.source)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/chart/template")
async def get_chart_template(current_user: User = Depends(require_permission("accounting:chart_view"))):
    """The Excel model to fill with the PGC or the company's own chart."""
    return Response(content=excel_template(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="plano_de_contas_modelo.xlsx"'})


@router.post("/chart/import")
async def post_chart_import(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("accounting:chart_manage"))):
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ficheiro demasiado grande (máximo 5 MB)")
    try:
        return await import_chart(db, current_user.company_id, content)
    except ChartImportError as e:  # every wrong row, for the screen to list
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(e), "errors": e.errors})
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/accounts", status_code=status.HTTP_201_CREATED)
async def post_account(payload: AccountCreateRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        return _account(await create_account(db, current_user.company_id, payload.code, payload.name))
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.put("/accounts/{account_id}")
async def put_account(account_id: uuid.UUID, payload: AccountUpdateRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        return _account(await update_account(db, current_user.company_id, account_id, payload.name, payload.is_active))
    except AccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_account(account_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await delete_account(db, current_user.company_id, account_id)
    except AccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
