"""
Contabilidade - the reports read from the posted entries (LANCADO; the drafts never count).

  - trial_balance (balancete): every account of the chart with its balance before the period (saldo inicial), its
    debits and credits in the period and its balance at the end - an account's figures include those of its
    sub-accounts (45 = 45.1 + 45.2...), the classes add up to the totals. By default only the accounts that moved or
    hold a balance; max_level keeps the upper levels only (the classes, the accounts...);
  - account_ledger (extrato de conta): the lines of one account (and of its sub-accounts) in the period, with the
    running balance from the balance before it.
A balance is debit - credit: > 0 devedor (D), < 0 credor (C).
"""
import io
import uuid
from collections import defaultdict
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account
from app.models.journal import Journal, JournalEntry, JournalEntryLine
from app.services.chart_of_accounts_service import sort_key
from app.services.journal_service import label_of

ZERO = Decimal("0.00")


class ReportError(Exception):
    pass


def _check_dates(date_from: date, date_to: date) -> None:
    if date_to < date_from:
        raise ReportError("A data final não pode ser anterior à data inicial")


async def _accounts(db: AsyncSession, company_id: uuid.UUID) -> list[Account]:
    return sorted((await db.execute(select(Account).where(Account.company_id == company_id))).scalars().all(),
                  key=lambda a: sort_key(a.code))


async def trial_balance(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date,
                        max_level: int | None = None, all_accounts: bool = False) -> dict:
    _check_dates(date_from, date_to)
    before = JournalEntry.entry_date < date_from
    inside = JournalEntry.entry_date.between(date_from, date_to)
    rows = (await db.execute(
        select(JournalEntryLine.account_id,
               func.sum(case((before, JournalEntryLine.debit - JournalEntryLine.credit), else_=0)),
               func.sum(case((inside, JournalEntryLine.debit), else_=0)),
               func.sum(case((inside, JournalEntryLine.credit), else_=0)))
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .where(JournalEntry.company_id == company_id, JournalEntry.status == "LANCADO", JournalEntry.entry_date <= date_to)
        .group_by(JournalEntryLine.account_id)
    )).all()
    accounts = await _accounts(db, company_id)
    by_id = {a.id: a for a in accounts}
    figures: dict[uuid.UUID, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO, ZERO])  # opening, debit, credit
    for account_id, opening, debit, credit in rows:
        account = by_id.get(account_id)
        while account is not None:  # into the account and every account above it
            f = figures[account.id]
            f[0] += Decimal(opening or 0)
            f[1] += Decimal(debit or 0)
            f[2] += Decimal(credit or 0)
            account = by_id.get(account.parent_id)
    with_children = {a.parent_id for a in accounts if a.parent_id}
    out, totals = [], [ZERO, ZERO, ZERO, ZERO]
    for a in accounts:
        opening, debit, credit = figures.get(a.id, (ZERO, ZERO, ZERO))
        closing = opening + debit - credit
        if a.level == 1:
            for i, v in enumerate((opening, debit, credit, closing)):
                totals[i] += v
        if max_level and a.level > max_level:
            continue
        if not all_accounts and not (opening or debit or credit):
            continue
        out.append({"id": a.id, "code": a.code, "name": a.name, "level": a.level, "has_children": a.id in with_children,
                    "opening": opening, "debit": debit, "credit": credit, "closing": closing})
    return {"date_from": date_from, "date_to": date_to, "accounts": out,
            "totals": {"opening": totals[0], "debit": totals[1], "credit": totals[2], "closing": totals[3]}}


async def account_ledger(db: AsyncSession, company_id: uuid.UUID, account_id: uuid.UUID, date_from: date,
                         date_to: date) -> dict:
    _check_dates(date_from, date_to)
    accounts = await _accounts(db, company_id)
    account = next((a for a in accounts if a.id == account_id), None)
    if account is None:
        raise ReportError("Conta não encontrada")
    # the account and every account under it
    by_id = {a.id: a for a in accounts}

    def under(a: Account) -> bool:
        while a is not None:
            if a.id == account.id:
                return True
            a = by_id.get(a.parent_id)
        return False
    ids = [a.id for a in accounts if under(a)]
    codes = {a.id: (a.code, a.name) for a in accounts}
    base = (select(JournalEntryLine, JournalEntry, Journal.code)
            .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
            .join(Journal, Journal.id == JournalEntry.journal_id)
            .where(JournalEntry.company_id == company_id, JournalEntry.status == "LANCADO",
                   JournalEntryLine.account_id.in_(ids)))
    opening = (await db.execute(
        select(func.coalesce(func.sum(JournalEntryLine.debit - JournalEntryLine.credit), 0))
        .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
        .where(JournalEntry.company_id == company_id, JournalEntry.status == "LANCADO",
               JournalEntryLine.account_id.in_(ids), JournalEntry.entry_date < date_from)
    )).scalar_one()
    rows = (await db.execute(base.where(JournalEntry.entry_date.between(date_from, date_to))
                             .order_by(JournalEntry.entry_date, JournalEntry.posted_at, JournalEntryLine.position))).all()
    balance, lines, total_debit, total_credit = Decimal(opening), [], ZERO, ZERO
    for line, entry, journal_code in rows:
        balance += line.debit - line.credit
        total_debit += line.debit
        total_credit += line.credit
        code, name = codes[line.account_id]
        lines.append({"entry_id": entry.id, "date": entry.entry_date, "entry": label_of(journal_code, entry.year, entry.number),
                      "account_code": code, "account_name": name, "document_ref": entry.document_ref,
                      "description": line.description or entry.description, "debit": line.debit, "credit": line.credit,
                      "balance": balance})
    return {"account": {"id": account.id, "code": account.code, "name": account.name}, "date_from": date_from,
            "date_to": date_to, "opening": Decimal(opening), "lines": lines, "total_debit": total_debit,
            "total_credit": total_credit, "closing": balance}


def side(value: Decimal) -> str:
    """1 500,00 D / 1 500,00 C - the balance with its side (devedor / credor)."""
    if not value:
        return ""
    amount = f"{abs(value):,.2f}".replace(",", " ").replace(".", ",")
    return f"{amount} {'D' if value > 0 else 'C'}"


def trial_balance_excel(data: dict, company_name: str) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Balancete"
    ws.append([f"Balancete - {company_name}"])
    ws.append([f"De {data['date_from'].strftime('%d/%m/%Y')} a {data['date_to'].strftime('%d/%m/%Y')}"])
    ws.append([])
    headers = ("Conta", "Descrição", "Saldo inicial", "Débito", "Crédito", "Saldo final", "Natureza")
    ws.append(headers)
    for cell in ws[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
    ws["A1"].font = Font(bold=True, size=13)
    for row in data["accounts"]:
        closing = row["closing"]
        ws.append([row["code"], ("  " * (row["level"] - 1)) + row["name"], float(row["opening"]), float(row["debit"]),
                   float(row["credit"]), float(abs(closing)), "D" if closing > 0 else "C" if closing < 0 else ""])
        if row["level"] == 1:
            for cell in ws[ws.max_row]:
                cell.font = Font(bold=True)
    t = data["totals"]
    ws.append(["", "Totais", float(t["opening"]), float(t["debit"]), float(t["credit"]), float(abs(t["closing"])),
               "D" if t["closing"] > 0 else "C" if t["closing"] < 0 else ""])
    for cell in ws[ws.max_row]:
        cell.font = Font(bold=True)
    for col, width in zip("ABCDEFG", (14, 50, 16, 16, 16, 16, 9)):
        ws.column_dimensions[col].width = width
    for row in ws.iter_rows(min_row=5, min_col=3, max_col=6):
        for cell in row:
            cell.number_format = '#,##0.00'
            cell.alignment = Alignment(horizontal="right")
    for row in ws.iter_rows(min_row=5, min_col=1, max_col=1):
        for cell in row:
            cell.number_format = "@"
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
