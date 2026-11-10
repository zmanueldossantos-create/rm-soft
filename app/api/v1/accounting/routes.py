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
    IntegrationError, integrate_company, integrate_today, integration_status, set_include_training, set_integration_start,
)


class IncludeTrainingRequest(BaseModel):
    include_training: bool


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


@router.post("/integration/today")
async def post_integration_today(db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("accounting:entries_record"))):
    """Modo formação: everything now, today's stock too (the cost of today's sales...) - a demonstration in one go."""
    try:
        result = await integrate_today(db, current_user.company_id)
    except IntegrationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
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


# ---------- the reports: balancete and extrato de conta ----------

from app.services.accounting_reports_service import (  # noqa: E402
    ReportError, account_ledger, trial_balance, trial_balance_excel,
)


async def _company(db: AsyncSession, company_id: uuid.UUID) -> dict:
    from app.models.company import Company
    from app.services.cash_report_service import _company_dict
    return _company_dict(await db.get(Company, company_id))


async def _trial_balance(db, company_id, date_from, date_to, max_level, all_accounts):
    try:
        return await trial_balance(db, company_id, date_from, date_to, max_level, all_accounts)
    except ReportError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/trial-balance")
async def get_trial_balance(date_from: date, date_to: date, max_level: int | None = None, all_accounts: bool = False,
                            db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await _trial_balance(db, current_user.company_id, date_from, date_to, max_level, all_accounts)


@router.get("/trial-balance/excel")
async def get_trial_balance_excel(date_from: date, date_to: date, max_level: int | None = None, all_accounts: bool = False,
                                  db: AsyncSession = Depends(get_db),
                                  current_user: User = Depends(require_permission("accounting:entries_view"))):
    data = await _trial_balance(db, current_user.company_id, date_from, date_to, max_level, all_accounts)
    company = await _company(db, current_user.company_id)
    return Response(content=trial_balance_excel(data, company["name"]),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="balancete_{date_from}_{date_to}.xlsx"'})


@router.get("/trial-balance/pdf")
async def get_trial_balance_pdf(date_from: date, date_to: date, max_level: int | None = None, all_accounts: bool = False,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("accounting:entries_view"))):
    from app.utils.accounting_pdf import generate_trial_balance_pdf
    data = await _trial_balance(db, current_user.company_id, date_from, date_to, max_level, all_accounts)
    pdf = generate_trial_balance_pdf(data, await _company(db, current_user.company_id))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="balancete_{date_from}_{date_to}.pdf"'})


async def _ledger(db, company_id, account_id, date_from, date_to):
    try:
        return await account_ledger(db, company_id, account_id, date_from, date_to)
    except ReportError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/ledger/{account_id}")
async def get_account_ledger(account_id: uuid.UUID, date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                             current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await _ledger(db, current_user.company_id, account_id, date_from, date_to)


@router.get("/ledger/{account_id}/pdf")
async def get_account_ledger_pdf(account_id: uuid.UUID, date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("accounting:entries_view"))):
    from app.utils.accounting_pdf import generate_account_ledger_pdf
    data = await _ledger(db, current_user.company_id, account_id, date_from, date_to)
    pdf = generate_account_ledger_pdf(data, await _company(db, current_user.company_id))
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="extrato_{data["account"]["code"]}.pdf"'})


# ---------- the stock in the accounting ----------

from app.services.account_mapping_service import set_inventory_system, set_stock_type_account  # noqa: E402


class InventorySystemRequest(BaseModel):
    inventory_system: str  # PERMANENTE or INTERMITENTE


@router.put("/stock-type-accounts/{movement_type_id}")
async def put_stock_type_account(movement_type_id: uuid.UUID, payload: MappingRequest, db: AsyncSession = Depends(get_db),
                                 current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await set_stock_type_account(db, current_user.company_id, movement_type_id, payload.account_id)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await list_mappings(db, current_user.company_id)


@router.put("/inventory-system")
async def put_inventory_system(payload: InventorySystemRequest, db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_permission("accounting:chart_manage"))):
    try:
        await set_inventory_system(db, current_user.company_id, payload.inventory_system)
    except ChartError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await list_mappings(db, current_user.company_id)


# ---------- the financial statements (Balanço, Demonstração de resultados) ----------

from app.services.financial_statements_service import StatementError, financial_statements, statements_excel  # noqa: E402


async def _statements(db, company_id, date_from, date_to):
    try:
        return await financial_statements(db, company_id, date_from, date_to)
    except StatementError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/financial-statements")
async def get_financial_statements(date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await _statements(db, current_user.company_id, date_from, date_to)


@router.get("/financial-statements/excel")
async def get_financial_statements_excel(date_from: date, date_to: date, db: AsyncSession = Depends(get_db),
                                         current_user: User = Depends(require_permission("accounting:entries_view"))):
    data = await _statements(db, current_user.company_id, date_from, date_to)
    company = await _company(db, current_user.company_id)
    return Response(content=statements_excel(data, company["name"]),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="demonstracoes_{date_to}.xlsx"'})


@router.get("/financial-statements/pdf")
async def get_financial_statements_pdf(date_from: date, date_to: date, which: str = "both", db: AsyncSession = Depends(get_db),
                                       current_user: User = Depends(require_permission("accounting:entries_view"))):
    from app.utils.accounting_pdf import generate_statements_pdf
    data = await _statements(db, current_user.company_id, date_from, date_to)
    pdf = generate_statements_pdf(data, await _company(db, current_user.company_id), which if which in ("balance", "income") else "both")
    return Response(content=pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="demonstracoes_{date_to}.pdf"'})


# ---------- the closing of the year ----------

from app.services.year_closing_service import (  # noqa: E402
    CLOSING, OPENING, YearClosingError, cancel, close_year, open_next_year, year_status,
)


@router.get("/year-closing/{year}")
async def get_year_closing(year: int, db: AsyncSession = Depends(get_db),
                           current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await year_status(db, current_user.company_id, year)


@router.post("/year-closing/{year}/{action}")
async def post_year_closing(year: int, action: str, db: AsyncSession = Depends(get_db),
                            current_user: User = Depends(require_permission("accounting:year_close"))):
    """action: close (apuramento), open (abertura do ano seguinte), cancel-close, cancel-open."""
    company_id, user_id = current_user.company_id, current_user.id
    try:
        if action == "close":
            await close_year(db, company_id, user_id, year)
        elif action == "open":
            await open_next_year(db, company_id, user_id, year)
        elif action == "cancel-close":
            await cancel(db, company_id, user_id, year, CLOSING)
        elif action == "cancel-open":
            await cancel(db, company_id, user_id, year, OPENING)
        else:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Ação desconhecida")
    except YearClosingError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await year_status(db, company_id, year)


# ---------- the opening balances (saldos iniciais) ----------

from fastapi import Form  # noqa: E402

from app.services.opening_balances_service import (  # noqa: E402
    OpeningBalancesError, cancel_opening_balances, import_opening_balances, opening_balances,
)
from app.services.opening_balances_service import excel_template as opening_template  # noqa: E402


@router.get("/opening-balances")
async def get_opening_balances(db: AsyncSession = Depends(get_db),
                               current_user: User = Depends(require_permission("accounting:entries_view"))):
    return await opening_balances(db, current_user.company_id)


@router.get("/opening-balances/template")
async def get_opening_balances_template(current_user: User = Depends(require_permission("accounting:entries_view"))):
    return Response(content=opening_template(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="saldos_iniciais_modelo.xlsx"'})


@router.post("/opening-balances/import")
async def post_opening_balances(entry_date: date = Form(...), file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_permission("accounting:entries_record"))):
    content = await file.read(MAX_UPLOAD + 1)
    if len(content) > MAX_UPLOAD:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ficheiro demasiado grande (máximo 5 MB)")
    try:
        await import_opening_balances(db, current_user.company_id, current_user.id, content, entry_date)
    except OpeningBalancesError as e:
        return JSONResponse(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, content={"detail": str(e), "errors": e.errors})
    return await opening_balances(db, current_user.company_id)


@router.post("/opening-balances/cancel")
async def post_cancel_opening_balances(db: AsyncSession = Depends(get_db),
                                       current_user: User = Depends(require_permission("accounting:entries_record"))):
    try:
        await cancel_opening_balances(db, current_user.company_id, current_user.id)
    except OpeningBalancesError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await opening_balances(db, current_user.company_id)


@router.put("/integration/training")
async def put_integration_training(payload: IncludeTrainingRequest, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_permission("accounting:chart_manage"))):
    """Modo formação: its documents in the accounting too (a demonstration, a training) - or no longer."""
    try:
        await set_include_training(db, current_user.company_id, payload.include_training)
    except IntegrationError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return await integration_status(db, current_user.company_id)
