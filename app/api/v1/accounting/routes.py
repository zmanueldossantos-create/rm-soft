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


# ---------- «Contas por operação» and the sub-accounts made by the system ----------

from app.services.account_mapping_service import (  # noqa: E402
    apply_suggestions, list_mappings, set_mapping, set_options, sync_subaccounts,
)


class MappingRequest(BaseModel):
    account_id: uuid.UUID | None = None  # None: no account for this operation


class MappingOptionsRequest(BaseModel):
    subaccount_per_customer: bool
    subaccount_per_supplier: bool


@router.get("/mappings")
async def get_mappings(db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:chart_view"))):
    return await list_mappings(db, current_user.company_id)


@router.put("/mappings/{key}")
async def put_mapping(key: str, payload: MappingRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await set_mapping(db, current_user.company_id, key, payload.account_id)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await list_mappings(db, current_user.company_id)


@router.put("/mappings-options")
async def put_mapping_options(payload: MappingOptionsRequest, db: AsyncSession = Depends(get_db),
                              current_user: User = Depends(require_permission("accounting:chart_manage"))):
    await set_options(db, current_user.company_id, payload.subaccount_per_customer, payload.subaccount_per_supplier)
    return await list_mappings(db, current_user.company_id)


@router.post("/mappings/suggestions")
async def post_mapping_suggestions(db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("accounting:chart_manage"))):
    applied = await apply_suggestions(db, current_user.company_id)
    return {"applied": applied, **(await list_mappings(db, current_user.company_id))}


@router.post("/subaccounts/sync")
async def post_sync_subaccounts(db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        return await sync_subaccounts(db, current_user.company_id)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


# ---------- the journals (diários) and the entries (lançamentos) ----------

from datetime import date  # noqa: E402
from decimal import Decimal  # noqa: E402

from fastapi import Query  # noqa: E402

from app.services.journal_service import (  # noqa: E402
    EntryNotFoundError, JournalError, JournalNotFoundError, create_journal, delete_entry, delete_journal, get_entry,
    list_entries, list_journals, post_entry, reverse_entry, save_entry, update_journal,
)


class JournalCreateRequest(BaseModel):
    code: str
    name: str


class JournalUpdateRequest(BaseModel):
    name: str
    is_active: bool = True


class EntryLineRequest(BaseModel):
    account_id: uuid.UUID | None = None
    description: str | None = None
    debit: Decimal = Decimal("0")
    credit: Decimal = Decimal("0")


class EntryRequest(BaseModel):
    journal_id: uuid.UUID
    entry_date: date
    description: str
    document_ref: str | None = None
    lines: list[EntryLineRequest] = []
    post: bool = False  # True: saved and posted in one step («Lançar»)


class ReverseRequest(BaseModel):
    entry_date: date


def _journal_out(j) -> dict:
    return {"id": j.id, "code": j.code, "name": j.name, "is_active": j.is_active}


def _refused(e: Exception) -> HTTPException:
    if isinstance(e, (JournalNotFoundError, EntryNotFoundError)):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


_ERRORS = (JournalError, JournalNotFoundError, EntryNotFoundError)


@router.get("/journals")
async def get_journals(db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await list_journals(db, current_user.company_id)


@router.post("/journals", status_code=status.HTTP_201_CREATED)
async def post_journal(payload: JournalCreateRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:journals_manage"))):
    try:
        return _journal_out(await create_journal(db, current_user.company_id, payload.code, payload.name))
    except _ERRORS as e:
        raise _refused(e)


@router.put("/journals/{journal_id}")
async def put_journal(journal_id: uuid.UUID, payload: JournalUpdateRequest, db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("accounting:journals_manage"))):
    try:
        return _journal_out(await update_journal(db, current_user.company_id, journal_id, payload.name, payload.is_active))
    except _ERRORS as e:
        raise _refused(e)


@router.delete("/journals/{journal_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_journal(journal_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("accounting:journals_manage"))):
    try:
        await delete_journal(db, current_user.company_id, journal_id)
    except _ERRORS as e:
        raise _refused(e)


@router.get("/entries")
async def get_entries(journal_id: uuid.UUID | None = None, status_filter: str | None = Query(None, alias="status"),
                      date_from: date | None = None, date_to: date | None = None, q: str | None = None,
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await list_entries(db, current_user.company_id, journal_id=journal_id, status=status_filter,
                              date_from=date_from, date_to=date_to, search=q)


@router.get("/entries/{entry_id}")
async def get_one_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                        current_user: User = Depends(require_permission("accounting:entries_view"))):
    try:
        return await get_entry(db, current_user.company_id, entry_id)
    except _ERRORS as e:
        raise _refused(e)


async def _save(db, current_user, entry_id, payload: EntryRequest) -> dict:
    try:
        entry = await save_entry(
            db, current_user.company_id, current_user.id, entry_id=entry_id, journal_id=payload.journal_id,
            entry_date=payload.entry_date, description=payload.description, document_ref=payload.document_ref,
            lines=[l.model_dump() for l in payload.lines], post=payload.post)
        return await get_entry(db, current_user.company_id, entry.id)
    except _ERRORS as e:
        raise _refused(e)


@router.post("/entries", status_code=status.HTTP_201_CREATED)
async def post_new_entry(payload: EntryRequest, db: AsyncSession = Depends(get_db),
                         current_user: User = Depends(require_permission("accounting:entries_record"))):
    return await _save(db, current_user, None, payload)


@router.put("/entries/{entry_id}")
async def put_entry(entry_id: uuid.UUID, payload: EntryRequest, db: AsyncSession = Depends(get_db),
                    current_user: User = Depends(require_permission("accounting:entries_record"))):
    return await _save(db, current_user, entry_id, payload)


@router.post("/entries/{entry_id}/post")
async def post_draft(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                     current_user: User = Depends(require_permission("accounting:entries_record"))):
    try:
        entry = await post_entry(db, current_user.company_id, current_user.id, entry_id)
        return await get_entry(db, current_user.company_id, entry.id)
    except _ERRORS as e:
        raise _refused(e)


@router.post("/entries/{entry_id}/reverse")
async def post_reverse(entry_id: uuid.UUID, payload: ReverseRequest, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:entries_record"))):
    try:
        entry = await reverse_entry(db, current_user.company_id, current_user.id, entry_id, payload.entry_date)
        return await get_entry(db, current_user.company_id, entry.id)
    except _ERRORS as e:
        raise _refused(e)


@router.delete("/entries/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_entry(entry_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                       current_user: User = Depends(require_permission("accounting:entries_record"))):
    try:
        await delete_entry(db, current_user.company_id, entry_id)
    except _ERRORS as e:
        raise _refused(e)


# ---------- the entries made by the system from the documents (integração) ----------

from app.services.accounting_integration_service import (  # noqa: E402
    IntegrationError, integrate_company, integration_status, set_integration_start,
)


class IntegrationStartRequest(BaseModel):
    integration_start: date


@router.get("/integration")
async def get_integration(db: AsyncSession = Depends(get_db),
                          current_user: User = Depends(require_permission("accounting:entries_view"))):
    """The day the integration starts from, how many documents wait for their entry, and those refused (and why)."""
    return await integration_status(db, current_user.company_id)


@router.post("/integration/run")
async def post_integration_run(db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_permission("accounting:entries_record"))):
    """At once, instead of waiting for the next round (every minute)."""
    result = await integrate_company(db, current_user.company_id, limit=5000)
    return {"posted": result["posted"], "refused": result["pending"], **await integration_status(db, current_user.company_id)}


@router.put("/integration/start")
async def put_integration_start(payload: IntegrationStartRequest, db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await set_integration_start(db, current_user.company_id, payload.integration_start)
    except IntegrationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await integration_status(db, current_user.company_id)


# ---------- the account of each treasury reason ----------

from app.services.account_mapping_service import set_reason_account  # noqa: E402


@router.put("/reason-accounts/{reason_id}")
async def put_reason_account(reason_id: uuid.UUID, payload: MappingRequest, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await set_reason_account(db, current_user.company_id, reason_id, payload.account_id)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await list_mappings(db, current_user.company_id)
