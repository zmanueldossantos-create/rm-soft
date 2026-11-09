"""
Contabilidade - the closing of the year (fecho do exercício). The balance sheet accounts are never closed and
reopened: their balance runs on from one year to the next (the balancete and the Balanço read every entry up to their
date). The closing does what the law asks of the result:

  1. Apuramento de resultados (journal APU, on 31/12): each account of the classes 6 and 7 closed into the result
     account of its kind (61 -> 82.1 ... 69 -> 86.1, 79 -> 86.2 - app.data.financial_statements), then the results 82
     to 87 moved into the net result (88.1, made under 88 when the chart lacks it) through their transfer accounts
     (82.19, 83.9 ... 87.9). Refused while the year has drafts or documents waiting in «Por integrar», or while the
     year before has movements of the classes 6 and 7 not closed. Cancelled by its estorno, while the next year is not
     opened.
  2. Abertura do ano seguinte (journal ABE, on 01/01 of the next year): the net result moved into 81 Resultados
     transitados. Its sharing out (reserves, dividends) is the accountant's own entry. Cancelled by its estorno.

Both entries carry their kind (source_kind CLOSING / OPENING, their estornos too): the Demonstração de resultados leaves
them out, and they are cancelled from here only.
"""
import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.financial_statements import CLOSING_TARGETS, NET_RESULT, RESULT_TRANSFERS, RETAINED_EARNINGS
from app.models.account import Account, AccountingSettings
from app.models.journal import Journal, JournalEntry, JournalEntryLine, PendingIntegration
from app.services.journal_service import JournalError, label_of, reverse_entry, save_entry

ZERO = Decimal("0.00")
CLOSING, OPENING = "CLOSING", "OPENING"
JOURNALS = {"APU": "Apuramento de resultados", "ABE": "Abertura"}


class YearClosingError(Exception):
    pass


async def _journal(db: AsyncSession, company_id: uuid.UUID, code: str) -> Journal:
    journal = (await db.execute(select(Journal).where(Journal.company_id == company_id, Journal.code == code))).scalar_one_or_none()
    if journal is None:  # the companies started before the journal existed
        journal = Journal(company_id=company_id, code=code, name=JOURNALS[code], is_active=True)
        db.add(journal)
        await db.flush()
    return journal


async def _active(db: AsyncSession, company_id: uuid.UUID, kind: str, day: date) -> JournalEntry | None:
    """The closing (or opening) entry of that day still in force: not an estorno, not reversed."""
    entries = (await db.execute(select(JournalEntry).where(
        JournalEntry.company_id == company_id, JournalEntry.source_kind == kind, JournalEntry.entry_date == day,
        JournalEntry.status == "LANCADO", JournalEntry.reversal_of_id.is_(None)))).scalars().all()
    for entry in entries:
        reversed_ = (await db.execute(select(JournalEntry.id).where(JournalEntry.reversal_of_id == entry.id))).first()
        if reversed_ is None:
            return entry
    return None


async def _balances(db: AsyncSession, company_id: uuid.UUID, date_from: date | None, date_to: date) -> dict[str, Decimal]:
    query = (select(Account.code, func.sum(JournalEntryLine.debit - JournalEntryLine.credit))
             .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
             .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
             .where(JournalEntry.company_id == company_id, JournalEntry.status == "LANCADO", JournalEntry.entry_date <= date_to)
             .group_by(Account.code))
    if date_from is not None:
        query = query.where(JournalEntry.entry_date >= date_from)
    return {code: Decimal(v or 0) for code, v in (await db.execute(query)).all() if v}


async def _accounts(db: AsyncSession, company_id: uuid.UUID) -> dict[str, Account]:
    return {a.code: a for a in (await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all()}


async def _net_result_account(db: AsyncSession, company_id: uuid.UUID, accounts: dict[str, Account]) -> Account:
    code, name, parent = NET_RESULT
    if code in accounts:
        return accounts[code]
    if parent not in accounts:
        raise YearClosingError(f"O plano de contas não tem a conta {parent} (Resultado líquido do exercício)")
    from app.services.chart_of_accounts_service import create_account
    account = await create_account(db, company_id, code, name)
    accounts[code] = account
    return account


def _label(entry: JournalEntry | None, journal_code: str) -> dict | None:
    if entry is None:
        return None
    return {"id": entry.id, "label": label_of(journal_code, entry.year, entry.number), "date": entry.entry_date}


async def year_status(db: AsyncSession, company_id: uuid.UUID, year: int) -> dict:
    """Where the year stands: its result, its apuramento and its abertura, and what still stops the apuramento."""
    end, start = date(year, 12, 31), date(year, 1, 1)
    closing = await _active(db, company_id, CLOSING, end)
    opening = await _active(db, company_id, OPENING, date(year + 1, 1, 1))
    from app.services.financial_statements_service import financial_statements
    result = next(r["value"] for r in (await financial_statements(db, company_id, start, end))["income_statement"]
                  if r["key"] == "T_LIQUIDO")
    drafts = (await db.execute(select(func.count(JournalEntry.id)).where(
        JournalEntry.company_id == company_id, JournalEntry.status == "RASCUNHO",
        JournalEntry.entry_date.between(start, end)))).scalar_one()
    pending = (await db.execute(select(func.count(PendingIntegration.id)).where(
        PendingIntegration.company_id == company_id, PendingIntegration.document_date.between(start, end)))).scalar_one()
    previous = await _balances(db, company_id, date(year - 1, 1, 1), date(year - 1, 12, 31))
    previous_open = any(code[:1] in "67" and v for code, v in previous.items()) and \
        await _active(db, company_id, CLOSING, date(year - 1, 12, 31)) is None
    checks = [
        {"ok": drafts == 0, "label": "Nenhum rascunho no exercício" if not drafts else f"{drafts} rascunho(s) no exercício - lance-os ou apague-os"},
        {"ok": pending == 0, "label": "Nenhum documento por integrar" if not pending else f"{pending} documento(s) por integrar no exercício"},
        {"ok": not previous_open, "label": f"Exercício {year - 1} apurado" if previous_open else f"Exercício {year - 1} sem resultados por apurar"},
    ]
    return {"year": year, "result": result, "closing": _label(closing, "APU"), "opening": _label(opening, "ABE"),
            "checks": checks, "can_close": closing is None and all(c["ok"] for c in checks),
            "can_open": closing is not None and opening is None}


async def close_year(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, year: int) -> JournalEntry:
    """The apuramento de resultados of the year, on 31/12 - see the module docstring."""
    settings = await db.get(AccountingSettings, company_id)
    if settings is None or settings.chart_source is None:
        raise YearClosingError("Comece primeiro o plano de contas")
    from app.services.accounting_integration_service import integrate_company
    await integrate_company(db, company_id)  # the documents still to post, first
    status = await year_status(db, company_id, year)
    if status["closing"]:
        raise YearClosingError(f"O exercício {year} já está apurado ({status['closing']['label']})")
    refused = [c["label"] for c in status["checks"] if not c["ok"]]
    if refused:
        raise YearClosingError("Não é possível apurar: " + "; ".join(refused))
    end = date(year, 12, 31)
    balances = await _balances(db, company_id, date(year, 1, 1), end)
    accounts = await _accounts(db, company_id)

    def account(code: str) -> Account:
        if code not in accounts:
            raise YearClosingError(f"O plano de contas não tem a conta {code}, necessária ao apuramento")
        return accounts[code]

    lines, targets = [], {}
    for code, balance in sorted(balances.items()):
        if code[:1] not in "67":
            continue
        target = CLOSING_TARGETS.get(code[:2])
        if target is None:
            raise YearClosingError(f"A conta {code} não tem conta de resultados no apuramento")
        lines.append(_line(account(code), -balance, "Apuramento"))
        targets[target] = targets.get(target, ZERO) + balance
    for target, amount in targets.items():
        lines.append(_line(account(target), amount, "Apuramento"))
    # the results 82 to 87 (those just made and those typed in the year, the tax 87.1) into the net result
    groups = {group: ZERO for group in RESULT_TRANSFERS}
    for code, balance in list(balances.items()) + list(targets.items()):
        group = code[:2]
        if group in groups and code != RESULT_TRANSFERS[group]:
            groups[group] += balance
    net_account = await _net_result_account(db, company_id, accounts)
    net = ZERO
    for group, amount in groups.items():
        if amount:
            lines.append(_line(account(RESULT_TRANSFERS[group]), -amount, "Transferência para resultados líquidos"))
            net += amount
    if net:
        lines.append(_line(net_account, net, "Resultado líquido do exercício"))
    lines = [l for l in lines if l["debit"] or l["credit"]]
    if not lines:
        raise YearClosingError(f"O exercício {year} não tem resultados a apurar")
    journal = await _journal(db, company_id, "APU")
    try:
        return await save_entry(db, company_id, user_id, entry_id=None, journal_id=journal.id, entry_date=end,
                                description=f"Apuramento de resultados do exercício {year}", document_ref=f"Exercício {year}",
                                lines=lines, post=True, source=(CLOSING, uuid.uuid4()))
    except JournalError as e:
        raise YearClosingError(str(e))


def _line(account: Account, amount: Decimal, description: str) -> dict:
    """amount > 0: a debit, < 0: a credit."""
    amount = amount.quantize(Decimal("0.01"))
    return {"account_id": account.id, "description": description,
            "debit": amount if amount > 0 else ZERO, "credit": -amount if amount < 0 else ZERO}


async def open_next_year(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, year: int) -> JournalEntry:
    """The abertura of year + 1, on 01/01: the net result of the year into Resultados transitados."""
    status = await year_status(db, company_id, year)
    if not status["closing"]:
        raise YearClosingError(f"Faça primeiro o apuramento do exercício {year}")
    if status["opening"]:
        raise YearClosingError(f"O exercício {year + 1} já foi aberto ({status['opening']['label']})")
    accounts = await _accounts(db, company_id)
    net_account = accounts.get(NET_RESULT[0])
    if RETAINED_EARNINGS not in accounts:
        raise YearClosingError(f"O plano de contas não tem a conta {RETAINED_EARNINGS} (Resultados transitados)")
    net = (await _balances(db, company_id, None, date(year, 12, 31))).get(NET_RESULT[0], ZERO) if net_account else ZERO
    if not net:
        raise YearClosingError(f"O resultado do exercício {year} é nulo - nada a transitar")
    journal = await _journal(db, company_id, "ABE")
    try:
        return await save_entry(
            db, company_id, user_id, entry_id=None, journal_id=journal.id, entry_date=date(year + 1, 1, 1),
            description=f"Resultado do exercício {year} para resultados transitados", document_ref=f"Exercício {year}",
            lines=[_line(net_account, -net, f"Resultado de {year}"), _line(accounts[RETAINED_EARNINGS], net, f"Resultado de {year}")],
            post=True, source=(OPENING, uuid.uuid4()))
    except JournalError as e:
        raise YearClosingError(str(e))


async def cancel(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, year: int, which: str) -> JournalEntry:
    """The estorno of the apuramento (which = CLOSING: only while the next year is not opened) or of the abertura."""
    status = await year_status(db, company_id, year)
    if which == CLOSING:
        if status["opening"]:
            raise YearClosingError(f"Anule primeiro a abertura do exercício {year + 1}")
        target, day = status["closing"], date(year, 12, 31)
    else:
        target, day = status["opening"], date(year + 1, 1, 1)
    if target is None:
        raise YearClosingError("Nada a anular")
    try:
        return await reverse_entry(db, company_id, user_id, target["id"], day, system=True)
    except JournalError as e:
        raise YearClosingError(str(e))
