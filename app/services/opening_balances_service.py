"""
Contabilidade - the opening balances (saldos iniciais) of a company that starts here coming from another program: the
balances of its accounts on the starting day, typed in the Excel model (Código, Descrição, Débito, Crédito - one row
per last-level account), imported in one entry of the journal ABE.

All or nothing, every wrong row listed: each account must exist in the chart, be a last-level one and active; a row has
a debit or a credit; the totals must be equal. No account is created on the way (a typing mistake would become an
account): the chart is imported first when needed. A new import cancels the previous one (its estorno) and posts the
new file - a corrected file is imported again, without duplicates. The entry is cancelled from its own screen only
(journal_service.PROTECTED_SOURCES). The stock quantities are not here: only the value of the stock, in the accounts.

A bank account's row (its sub-account, 43.1.x) is also its opening balance in Tesouraria › Bancos, on the same day:
typed once. A new import replaces it; a bank no longer in the file, or the import cancelled, gets its Tesouraria
balance back to «por definir» - unless it was changed there since (then it is the company's own and stays).
"""
import io
import uuid
from datetime import date
from decimal import Decimal, InvalidOperation

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Font, PatternFill
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountingSettings, AccountLink
from app.models.company_bank_account import CompanyBankAccount
from app.models.journal import JournalEntry, JournalEntryLine
from app.services.chart_of_accounts_service import normalize_code
from app.services.journal_service import JournalError, check_entry_date, label_of, reverse_entry, save_entry

SOURCE = "OPENING_BALANCES"
HEADERS = ("Código", "Descrição", "Débito", "Crédito")
SHEET = "Saldos iniciais"
MAX_ROWS = 3000
CENT = Decimal("0.01")


class OpeningBalancesError(Exception):
    def __init__(self, message: str, errors: list[str] | None = None):
        super().__init__(message)
        self.errors = errors or []


async def excel_template(db: AsyncSession, company_id: uuid.UUID) -> bytes:
    """The model to fill: the company's own bank and till sub-accounts and the capital already listed, amounts empty
    (no example figures in the rows - a model imported unchanged would post them); the example is in «Instruções»."""
    links = (await db.execute(select(Account.code, Account.name).join(AccountLink, AccountLink.account_id == Account.id)
                              .where(AccountLink.company_id == company_id, AccountLink.entity_kind.in_(("BANK", "TILL")))
                              .order_by(Account.code))).all()
    capital = (await db.execute(select(Account.code, Account.name).where(
        Account.company_id == company_id, Account.code == "51"))).first()
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(HEADERS)
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
    for code, name in [*links, *([capital] if capital else [])]:
        ws.append((code, name, None, None))
    for cells in ws.iter_rows(min_row=1, max_row=MAX_ROWS, min_col=1, max_col=1):
        for cell in cells:
            cell.number_format = "@"  # 45.10 stays 45.10
    for cells in ws.iter_rows(min_row=2, max_row=MAX_ROWS, min_col=3, max_col=4):
        for cell in cells:
            cell.number_format = "#,##0.00"
    ws.column_dimensions["A"].width = 16
    ws.column_dimensions["B"].width = 50
    ws.column_dimensions["C"].width = 18
    ws.column_dimensions["D"].width = 18
    notes = wb.create_sheet("Instruções")
    for line in (
        "Uma linha por conta de último nível (sem subcontas) com o seu saldo no dia do início: Débito ou Crédito.",
        "A Descrição é só para si - o sistema usa o Código. A conta tem de existir no plano de contas.",
        "O total do Débito tem de ser igual ao total do Crédito.",
        "Clientes e fornecedores: use as subcontas de cada um (ex.: 31.1.2.1.5) para ter o saldo de cada um.",
        "Existências: aqui só o valor contabilístico; as quantidades entram no Stock (entrada inicial).",
        "Importar de novo anula a importação anterior e lança o novo ficheiro.",
        "As contas dos bancos e das caixas e o capital já estão na folha: preencha os montantes e acrescente as outras.",
        "Uma linha sem montante é ignorada.",
        "Exemplo: 43.1.1 BAI Débito 2 500 000 · 45.1.1 Caixa Débito 150 000 · 26.1 Mercadorias Débito 800 000 · "
        "51 Capital Crédito 3 000 000 · 81 Resultados transitados Crédito 450 000.",
    ):
        notes.append((line,))
    notes.column_dimensions["A"].width = 120
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def _amount(raw, where: str, errors: list[str]) -> Decimal:
    if raw in (None, ""):
        return Decimal("0")
    try:
        value = Decimal(str(raw).replace(" ", "").replace(",", ".")) if isinstance(raw, str) else Decimal(str(raw))
    except (InvalidOperation, ValueError):
        errors.append(f"{where}: valor inválido ({raw})")
        return Decimal("0")
    if value < 0:
        errors.append(f"{where}: valor negativo - use a outra coluna")
    if value != value.quantize(CENT):
        errors.append(f"{where}: no máximo 2 casas decimais")
    return value.quantize(CENT)


def _read(content: bytes) -> list[tuple[int, str, Decimal, Decimal]]:
    try:
        wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    except Exception:  # noqa: BLE001 - not an Excel file
        raise OpeningBalancesError("O ficheiro não é um Excel (.xlsx) válido - use o modelo do sistema")
    ws = wb[SHEET] if SHEET in wb.sheetnames else wb.worksheets[0]
    rows, errors = [], []
    for index, row in enumerate(ws.iter_rows(values_only=True), start=1):
        if index == 1:
            continue
        row = tuple(row) + (None,) * 4
        code = normalize_code(row[0])
        if not code and row[2] in (None, "") and row[3] in (None, ""):
            continue
        where = f"Linha {index}"
        if not code:
            errors.append(f"{where}: falta o código da conta")
            continue
        rows.append((index, code, _amount(row[2], where, errors), _amount(row[3], where, errors)))
        if len(rows) > MAX_ROWS:
            raise OpeningBalancesError(f"O ficheiro tem mais de {MAX_ROWS} linhas")
    if errors:
        raise OpeningBalancesError("Corrija o ficheiro", errors)
    return rows


async def _active(db: AsyncSession, company_id: uuid.UUID) -> JournalEntry | None:
    entries = (await db.execute(select(JournalEntry).where(
        JournalEntry.company_id == company_id, JournalEntry.source_kind == SOURCE, JournalEntry.status == "LANCADO",
        JournalEntry.reversal_of_id.is_(None)).order_by(JournalEntry.created_at.desc()))).scalars().all()
    for entry in entries:
        if (await db.execute(select(JournalEntry.id).where(JournalEntry.reversal_of_id == entry.id))).first() is None:
            return entry
    return None


async def bank_openings(db: AsyncSession, company_id: uuid.UUID, entry: JournalEntry | None = None) -> dict:
    """The bank accounts in the opening balances in force (or in entry): bank account id -> (balance, day)."""
    entry = entry or await _active(db, company_id)
    if entry is None:
        return {}
    rows = (await db.execute(select(AccountLink.entity_id, JournalEntryLine.debit, JournalEntryLine.credit)
                             .join(AccountLink, and_(AccountLink.account_id == JournalEntryLine.account_id,
                                                     AccountLink.company_id == company_id, AccountLink.entity_kind == "BANK"))
                             .where(JournalEntryLine.entry_id == entry.id))).all()
    return {bank_id: (debit - credit, entry.entry_date) for bank_id, debit, credit in rows}


async def till_opening(db: AsyncSession, company_id: uuid.UUID, pos_id: uuid.UUID) -> float | None:
    """The cash a till (or the cofre) holds in the opening balances in force - the debit of its own sub-account
    (45.1.x) in the import, or None when the import has no line for it (or there is no import)."""
    entry = await _active(db, company_id)
    if entry is None:
        return None
    row = (await db.execute(select(JournalEntryLine.debit, JournalEntryLine.credit)
                            .join(AccountLink, and_(AccountLink.account_id == JournalEntryLine.account_id,
                                                    AccountLink.company_id == company_id, AccountLink.entity_kind == "TILL",
                                                    AccountLink.entity_id == pos_id))
                            .where(JournalEntryLine.entry_id == entry.id))).first()
    return float(row.debit - row.credit) if row is not None else None


async def _sync_banks(db: AsyncSession, now: dict, before: dict) -> None:
    """The Tesouraria opening balances follow the import (flush only, in the entry's transaction): now's banks get
    theirs; those only in before go back to «por definir» when nobody changed them since."""
    for bank_id, (amount, day) in now.items():
        account = await db.get(CompanyBankAccount, bank_id)
        account.opening_balance, account.opening_date = amount, day
    for bank_id, (amount, day) in before.items():
        if bank_id in now:
            continue
        account = await db.get(CompanyBankAccount, bank_id)
        if account is not None and Decimal(str(account.opening_balance or 0)) == amount and account.opening_date == day:
            account.opening_balance, account.opening_date = 0, None
    await db.flush()


async def opening_balances(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The imported opening balances in force (or none), and the day suggested for an import."""
    settings = await db.get(AccountingSettings, company_id)
    entry = await _active(db, company_id)
    out = {"suggested_date": settings.integration_start if settings else None, "entry": None}
    if entry is None:
        return out
    rows = (await db.execute(select(JournalEntryLine, Account.code, Account.name)
                             .join(Account, Account.id == JournalEntryLine.account_id)
                             .where(JournalEntryLine.entry_id == entry.id).order_by(JournalEntryLine.position))).all()
    out["entry"] = {
        "id": entry.id, "label": label_of("ABE", entry.year, entry.number), "date": entry.entry_date,
        "total": sum((l.debit for l, _, _ in rows), Decimal("0")),
        "lines": [{"code": code, "name": name, "debit": l.debit, "credit": l.credit} for l, code, name in rows],
    }
    return out


async def import_opening_balances(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, content: bytes,
                                  entry_date: date) -> JournalEntry:
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None:
        raise OpeningBalancesError("Comece primeiro o plano de contas")
    rows = _read(content)
    if not rows:
        raise OpeningBalancesError("O ficheiro não tem nenhum saldo")
    accounts = {a.code: a for a in (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()}
    parents = {a.parent_id for a in accounts.values() if a.parent_id}
    errors, seen, lines = [], {}, []
    for index, code, debit, credit in rows:
        where = f"Linha {index}"
        account = accounts.get(code)
        if account is None:
            errors.append(f"{where}: a conta {code} não existe no plano de contas")
        elif account.id in parents:
            errors.append(f"{where}: a conta {code} tem subcontas - use uma conta de último nível")
        elif not account.is_active:
            errors.append(f"{where}: a conta {code} está inativa")
        elif code in seen:
            errors.append(f"{where}: a conta {code} já aparece na linha {seen[code]}")
        elif debit and credit:
            errors.append(f"{where}: indique o débito ou o crédito, não os dois")
        if account is not None:
            seen.setdefault(code, index)
        if account is not None and (debit or credit) and not errors:
            lines.append({"account_id": account.id, "description": "Saldo inicial", "debit": debit, "credit": credit})
    debit_total = sum((d for _, _, d, _ in rows), Decimal("0"))
    credit_total = sum((c for _, _, _, c in rows), Decimal("0"))
    if debit_total != credit_total:
        diff = f"{abs(debit_total - credit_total):,.2f}".replace(",", " ").replace(".", ",")
        errors.append(f"O total do débito é diferente do total do crédito (diferença {diff})")
    if errors:
        raise OpeningBalancesError("Nada foi importado - corrija o ficheiro", errors[:300])
    if len(lines) < 2:
        raise OpeningBalancesError("O ficheiro não tem saldos a lançar")
    try:
        await check_entry_date(db, company_id, entry_date)
    except JournalError as e:
        raise OpeningBalancesError(str(e))
    from app.services.year_closing_service import _journal
    journal = await _journal(db, company_id, "ABE")
    previous = await _active(db, company_id)
    before = await bank_openings(db, company_id, previous) if previous is not None else {}

    async def banks(entry: JournalEntry) -> None:  # Tesouraria › Bancos: the same opening balances
        await _sync_banks(db, await bank_openings(db, company_id, entry), before)
    try:
        if previous is not None:  # the import before is cancelled: the new file replaces it
            await reverse_entry(db, company_id, user_id, previous.id, max(entry_date, previous.entry_date), system=True)
        return await save_entry(db, company_id, user_id, entry_id=None, journal_id=journal.id, entry_date=entry_date,
                                description="Saldos iniciais (importação)", document_ref="Saldos iniciais",
                                lines=lines, post=True, source=(SOURCE, uuid.uuid4()), on_saved=banks)
    except JournalError as e:
        raise OpeningBalancesError(str(e))


async def cancel_opening_balances(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None) -> None:
    entry = await _active(db, company_id)
    if entry is None:
        raise OpeningBalancesError("Não há saldos iniciais importados")
    before = await bank_openings(db, company_id, entry)

    async def banks(_estorno: JournalEntry) -> None:  # Tesouraria › Bancos: back to «por definir»
        await _sync_banks(db, {}, before)
    try:
        await reverse_entry(db, company_id, user_id, entry.id, entry.entry_date, system=True, on_saved=banks)
    except JournalError as e:
        raise OpeningBalancesError(str(e))
