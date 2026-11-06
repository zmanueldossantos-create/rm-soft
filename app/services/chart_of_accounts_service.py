"""
Contabilidade - the company's chart of accounts (plano de contas), fully set by the company (app.models.account).

  - start_chart: the first choice - the PGC (the system's reference list, app.data.pgc_angola), the company's own
    chart (then imported from the Excel model), or empty (accounts typed one by one); the PGC may be loaded again later
    to get the accounts added to the reference list since (the existing ones are kept as they are);
  - the Excel model (excel_template) and its import (import_chart): an account per row, «Código» and «Descrição»;
    each code is created, or renamed when it exists; nothing is saved when a row is wrong - every wrong row is listed;
  - one account at a time: create (its parent must exist), rename, deactivate, delete (only an account without
    sub-accounts - and, once the entries exist, without entries).
Codes: a class is one digit («4»), an account of the class two («45»), its sub-accounts follow with points («45.1»,
«45.1.1»); the parent is the code without its last part. A code never changes once created.
"""
import io
import re
import uuid
from datetime import datetime, timezone

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.pgc_angola import PGC_ACCOUNTS
from app.models.account import CHART_SOURCES, Account, AccountingSettings

CODE_RE = re.compile(r"^[1-9]$|^[1-9]\d(\.\d{1,4})*$")
MAX_ROWS = 20000


class ChartError(Exception):
    """A chart operation refused (a code, a name, a parent, a state) - 422."""


class ChartImportError(ChartError):
    """The Excel import refused: every wrong row with its reason (nothing was saved)."""

    def __init__(self, errors: list[str]):
        super().__init__("O ficheiro tem erros - nada foi importado")
        self.errors = errors


class AccountNotFoundError(Exception):
    pass


def normalize_code(raw) -> str:
    """The code as typed - spaces removed; a whole number read by Excel (45.0) back to 45."""
    if raw is None:
        return ""
    if isinstance(raw, float) and raw.is_integer():
        raw = int(raw)
    return re.sub(r"\s+", "", str(raw))


def parent_code(code: str) -> str | None:
    if "." in code:
        return code.rsplit(".", 1)[0]
    return code[:-1] if len(code) > 1 else None


def level_of(code: str) -> int:
    return 1 if len(code) == 1 else 2 + code.count(".")


def sort_key(code: str) -> tuple:
    head, *rest = code.split(".")
    return tuple(int(c) for c in head) + tuple(int(p) for p in rest)


def check_code(code: str) -> None:
    if not CODE_RE.match(code):
        raise ChartError(f"Código «{code}» inválido - uma classe tem 1 algarismo (4), uma conta 2 (45), as subcontas "
                         "seguem com pontos (45.1, 45.1.1)")


async def _settings(db: AsyncSession, company_id: uuid.UUID) -> AccountingSettings:
    settings = await db.get(AccountingSettings, company_id)
    if settings is None:
        settings = AccountingSettings(company_id=company_id)
        db.add(settings)
    return settings


async def _accounts_by_code(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Account]:
    rows = (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()
    return {a.code: a for a in rows}


async def get_chart(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The chart, in the order of its codes, with how it was started."""
    accounts = sorted((await _accounts_by_code(db, company_id)).values(), key=lambda a: sort_key(a.code))
    with_children = {a.parent_id for a in accounts if a.parent_id is not None}
    from app.services.account_mapping_service import accounts_in_use
    in_use = await accounts_in_use(db, company_id)
    settings = await db.get(AccountingSettings, company_id)
    return {
        "source": settings.chart_source if settings else None,
        "started_at": settings.chart_started_at if settings else None,
        "accounts": [{
            "id": a.id, "code": a.code, "name": a.name, "parent_id": a.parent_id, "level": a.level,
            "is_active": a.is_active, "has_children": a.id in with_children, "in_use": in_use.get(a.id),
        } for a in accounts],
    }


async def accounts_with_entries(db: AsyncSession, company_id: uuid.UUID) -> set[uuid.UUID]:
    """The accounts that already have lines in the journal (draft or posted): they never get sub-accounts."""
    from app.models.journal import JournalEntry, JournalEntryLine
    return set((await db.execute(select(JournalEntryLine.account_id).join(
        JournalEntry, JournalEntry.id == JournalEntryLine.entry_id).where(JournalEntry.company_id == company_id)
        .distinct())).scalars().all())


async def _add(db: AsyncSession, company_id: uuid.UUID, existing: dict[str, Account], code: str, name: str,
               with_entries: set[uuid.UUID] | None = None) -> Account:
    parent = existing.get(parent_code(code)) if parent_code(code) else None
    if parent is not None and with_entries and parent.id in with_entries:
        raise ChartError(f"A conta {parent.code} já tem lançamentos - não pode ter subcontas")
    account = Account(company_id=company_id, code=code, name=name, parent_id=parent.id if parent else None,
                      level=level_of(code), is_active=True)
    db.add(account)
    await db.flush()
    existing[code] = account
    return account


async def start_chart(db: AsyncSession, company_id: uuid.UUID, source: str) -> dict:
    """The company's choice: PGC loads the reference list (the accounts it lacks - none is renamed); PROPRIO and VAZIO
    only record the choice (the chart is then imported, or typed). The choice may be made again (e.g. the PGC loaded
    on a chart started empty) - it never removes an account."""
    if source not in CHART_SOURCES:
        raise ChartError("Escolha PGC, plano próprio ou vazio")
    existing = await _accounts_by_code(db, company_id)
    if source == "PGC":
        with_entries = await accounts_with_entries(db, company_id)
        for code, name in sorted(PGC_ACCOUNTS, key=lambda row: sort_key(row[0])):
            parent = parent_code(code)
            # skipped: a PGC account under an account that has entries (and then its own sub-accounts)
            if code in existing or (parent and (parent not in existing or existing[parent].id in with_entries)):
                continue
            await _add(db, company_id, existing, code, name)
    settings = await _settings(db, company_id)
    settings.chart_source = source
    settings.chart_started_at = datetime.now(timezone.utc)
    if source == "PGC":  # «Contas por operação»: the PGC accounts suggested, where nothing is set yet
        from app.services.account_mapping_service import apply_suggestions
        await db.flush()
        await apply_suggestions(db, company_id, commit=False)
    from app.services.journal_service import ensure_default_journals
    await ensure_default_journals(db, company_id)  # VND, CMP, CX, BCO, OD, ABE - for a company without journals
    await db.commit()
    from app.services.account_mapping_service import sync_subaccounts
    await sync_subaccounts(db, company_id)  # the sub-accounts of the banks, tills, customers and suppliers, at once
    return await get_chart(db, company_id)


async def create_account(db: AsyncSession, company_id: uuid.UUID, code: str, name: str) -> Account:
    code, name = normalize_code(code), (name or "").strip()
    check_code(code)
    if not name:
        raise ChartError("Indique a descrição da conta")
    existing = await _accounts_by_code(db, company_id)
    if code in existing:
        raise ChartError(f"A conta {code} já existe")
    parent = parent_code(code)
    if parent and parent not in existing:
        raise ChartError(f"Crie primeiro a conta {parent} (a conta-mãe de {code})")
    account = await _add(db, company_id, existing, code, name[:200], await accounts_with_entries(db, company_id))
    await db.commit()
    await db.refresh(account)
    return account


async def _get_or_raise(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> Account:
    account = (await db.execute(select(Account).where(
        Account.id == account_id, Account.company_id == company_id))).scalar_one_or_none()
    if account is None:
        raise AccountNotFoundError("Conta não encontrada")
    return account


async def update_account(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, name: str,
                         is_active: bool) -> Account:
    """Renames or (de)activates an account - its code never changes."""
    account = await _get_or_raise(db, company_id, account_id)
    name = (name or "").strip()
    if not name:
        raise ChartError("Indique a descrição da conta")
    account.name, account.is_active = name[:200], is_active
    await db.commit()
    await db.refresh(account)
    return account


async def delete_account(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID) -> None:
    """Only an account without sub-accounts (and, with the accounting entries, without entries)."""
    account = await _get_or_raise(db, company_id, account_id)
    children = (await db.execute(select(func.count(Account.id)).where(Account.parent_id == account.id))).scalar_one()
    if children:
        raise ChartError(f"A conta {account.code} tem subcontas - apague-as primeiro, ou desative a conta")
    from app.services.account_mapping_service import accounts_in_use
    why = (await accounts_in_use(db, company_id)).get(account.id)
    if why:
        raise ChartError(f"A conta {account.code} {why} - não pode ser apagada")
    await db.delete(account)
    await db.commit()


# ---------- the Excel model and its import ----------

HEADERS = ("Código", "Descrição")


def excel_template() -> bytes:
    """The model to fill: «Código» (as text) and «Descrição», with examples, and a sheet that explains the rules."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Plano de contas"
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
    for code, name in (("4", "Meios monetários"), ("45", "Caixa"), ("45.1", "Caixa - sede"), ("45.1.1", "Caixa Balcão")):
        ws.append((code, name))
    for row in ws.iter_rows(min_row=1, max_row=5000, min_col=1, max_col=1):
        for cell in row:
            cell.number_format = "@"  # text: 45.10 stays 45.10 (a number would become 45.1)
    ws.column_dimensions["A"].width = 18
    ws.column_dimensions["B"].width = 60
    help_sheet = wb.create_sheet("Instruções")
    for line in (
        "Uma conta por linha: o Código e a Descrição. Apague os exemplos e cole o seu plano (o PGC ou o plano próprio).",
        "Classe: 1 algarismo (4). Conta da classe: 2 algarismos (45). Subcontas: com pontos (45.1, 45.1.1, 45.1.10).",
        "A conta-mãe de cada código tem de existir (no ficheiro ou já no sistema): 45.1.1 precisa de 45.1, 45.1 de 45, 45 de 4.",
        "A coluna Código está em formato texto: escreva 45.10 e não 45.1 se for a décima subconta.",
        "Uma conta que já existe é só renomeada; nenhuma conta é apagada pela importação.",
        "Se uma linha estiver errada, nada é importado: o sistema mostra todas as linhas a corrigir.",
    ):
        help_sheet.append((line,))
    help_sheet.column_dimensions["A"].width = 120
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _read_rows(content: bytes) -> list[tuple[int, str, str]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - not an Excel file
        raise ChartError("O ficheiro não é um Excel (.xlsx) válido - use o modelo do sistema")
    ws = wb["Plano de contas"] if "Plano de contas" in wb.sheetnames else wb.worksheets[0]
    rows = []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if index == 1:
            continue  # the headers
        code = normalize_code(row[0] if len(row) > 0 else None)
        name = str(row[1]).strip() if len(row) > 1 and row[1] is not None else ""
        if not code and not name:
            continue
        rows.append((index, code, name))
        if len(rows) > MAX_ROWS:
            raise ChartError(f"O ficheiro tem mais de {MAX_ROWS} contas")
    return rows


async def import_chart(db: AsyncSession, company_id: uuid.UUID, content: bytes) -> dict:
    """The filled model into the chart: {created, renamed, unchanged} - or ChartImportError with every wrong row."""
    rows = _read_rows(content)
    if not rows:
        raise ChartError("O ficheiro não tem nenhuma conta")
    existing = await _accounts_by_code(db, company_id)
    errors, seen, valid = [], {}, []
    for index, code, name in rows:
        if not name:
            errors.append(f"Linha {index}: a conta {code or '(sem código)'} não tem descrição")
            continue
        try:
            check_code(code)
        except ChartError as e:
            errors.append(f"Linha {index}: {e}")
            continue
        if code in seen:
            errors.append(f"Linha {index}: o código {code} já aparece na linha {seen[code]}")
            continue
        seen[code] = index
        valid.append((index, code, name[:200]))
    with_entries = await accounts_with_entries(db, company_id)
    for index, code, _name in valid:
        parent = parent_code(code)
        if parent and parent not in seen and parent not in existing:
            errors.append(f"Linha {index}: falta a conta-mãe {parent} de {code} (no ficheiro ou no sistema)")
        elif code not in existing and parent in existing and existing[parent].id in with_entries:
            errors.append(f"Linha {index}: a conta {parent} já tem lançamentos - não pode ter a subconta {code}")
    if errors:
        raise ChartImportError(errors[:200])

    created = renamed = unchanged = 0
    for _index, code, name in sorted(valid, key=lambda row: sort_key(row[1])):
        account = existing.get(code)
        if account is None:
            await _add(db, company_id, existing, code, name)
            created += 1
        elif account.name != name:
            account.name = name
            renamed += 1
        else:
            unchanged += 1
    settings = await _settings(db, company_id)
    if settings.chart_source is None:
        settings.chart_source, settings.chart_started_at = "PROPRIO", datetime.now(timezone.utc)
    from app.services.journal_service import ensure_default_journals
    await ensure_default_journals(db, company_id)
    await db.commit()
    return {"created": created, "renamed": renamed, "unchanged": unchanged}
