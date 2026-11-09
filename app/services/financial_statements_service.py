"""
Contabilidade - the financial statements of the PGC de Angola, read from the posted entries (LANCADO): the Balanço at
a date and the Demonstração de resultados por natureza of a period, each with the same figures one year before (the
column N-1). The lines and their accounts: app.data.financial_statements.

The Balanço adds up every account up to its date - the result of the year is still in the classes 6 and 7 before the
closing, in 82 to 88 after it: the line «Resultado líquido do exercício» takes both, so the Balanço balances at any
date. An account a line does not cover (a company's own chart with other codes) is listed: the Balanço would not
balance without it.
"""
import io
import uuid
from datetime import date
from decimal import Decimal

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.data.financial_statements import BALANCE_SHEET_ASSETS, BALANCE_SHEET_EQUITY_LIABILITIES, INCOME_STATEMENT, Line
from app.models.account import Account
from app.models.journal import JournalEntry, JournalEntryLine

ZERO = Decimal("0.00")
CLOSING_SOURCE = "CLOSING"  # the entries of the closing of the year (apuramento): never in the Demonstração de resultados


class StatementError(Exception):
    pass


def covers(prefix: str, code: str) -> bool:
    """«31» covers 31, 31.1, 31.1.2...; a class («6») covers every account of the class (61, 62.1...)."""
    if len(prefix) == 1:
        return code[:1] == prefix
    return code == prefix or code.startswith(prefix + ".")


async def _balances(db: AsyncSession, company_id: uuid.UUID, date_to: date, date_from: date | None = None,
                    without_closing: bool = False) -> dict[str, Decimal]:
    """debit - credit per account code, of the posted entries up to date_to (from date_from when given)."""
    query = (select(Account.code, func.sum(JournalEntryLine.debit - JournalEntryLine.credit))
             .join(JournalEntryLine, JournalEntryLine.account_id == Account.id)
             .join(JournalEntry, JournalEntry.id == JournalEntryLine.entry_id)
             .where(JournalEntry.company_id == company_id, JournalEntry.status == "LANCADO", JournalEntry.entry_date <= date_to)
             .group_by(Account.code))
    if date_from is not None:
        query = query.where(JournalEntry.entry_date >= date_from)
    if without_closing:
        query = query.where(func.coalesce(JournalEntry.source_kind, "") != CLOSING_SOURCE)
    return {code: Decimal(value or 0) for code, value in (await db.execute(query)).all()}


def _value(line: Line, balances: dict[str, Decimal], sign: int) -> Decimal:
    total = ZERO
    for code, balance in balances.items():
        for prefix, rule in line.accounts:
            if covers(prefix, code):
                if rule == "net" or (rule == "debit" and balance > 0) or (rule == "credit" and balance < 0):
                    total += balance
                break
    return total * sign


def _rows(lines: tuple[Line, ...], balances: dict[str, Decimal], previous: dict[str, Decimal], sign: int) -> list[dict]:
    values: dict[str, tuple[Decimal, Decimal]] = {}
    rows = []
    for line in lines:
        if line.kind == "section":
            rows.append({"key": line.key, "label": line.label, "kind": "section", "value": None, "previous": None})
            continue
        if line.kind == "total":
            value = sum((values[k][0] for k in line.sums), ZERO)
            prev = sum((values[k][1] for k in line.sums), ZERO)
        else:
            value, prev = _value(line, balances, sign), _value(line, previous, sign)
        values[line.key] = (value, prev)
        rows.append({"key": line.key, "label": line.label, "kind": line.kind, "value": value, "previous": prev})
    return rows


def _year_before(day: date) -> date:
    try:
        return day.replace(year=day.year - 1)
    except ValueError:  # 29 February
        return day.replace(year=day.year - 1, day=28)


def _unclassified(balances: dict[str, Decimal]) -> list[str]:
    prefixes = [p for line in BALANCE_SHEET_ASSETS + BALANCE_SHEET_EQUITY_LIABILITIES for p, _ in line.accounts]
    return sorted(code for code, balance in balances.items() if balance and not any(covers(p, code) for p in prefixes))


async def financial_statements(db: AsyncSession, company_id: uuid.UUID, date_from: date, date_to: date) -> dict:
    if date_to < date_from:
        raise StatementError("A data final não pode ser anterior à data inicial")
    prev_from, prev_to = _year_before(date_from), _year_before(date_to)
    at_end, at_prev_end = await _balances(db, company_id, date_to), await _balances(db, company_id, prev_to)
    assets = _rows(BALANCE_SHEET_ASSETS, at_end, at_prev_end, 1)
    equity = _rows(BALANCE_SHEET_EQUITY_LIABILITIES, at_end, at_prev_end, -1)
    total_assets = next(r for r in assets if r["key"] == "T_ACTIVO")
    total_other = next(r for r in equity if r["key"] == "T_CP_PASSIVO")
    period = await _balances(db, company_id, date_to, date_from, without_closing=True)
    prev_period = await _balances(db, company_id, prev_to, prev_from, without_closing=True)
    income = _rows(INCOME_STATEMENT, period, prev_period, -1)
    return {
        "date_from": date_from, "date_to": date_to, "previous_from": prev_from, "previous_to": prev_to,
        "balance_sheet": {
            "assets": assets, "equity_liabilities": equity,
            "balanced": total_assets["value"] == total_other["value"] and total_assets["previous"] == total_other["previous"],
            "unclassified": _unclassified(at_end),
        },
        "income_statement": income,
    }


# ---------- Excel ----------

def _sheet(ws, title: str, company_name: str, columns: tuple[str, str], blocks: list[tuple[str | None, list[dict]]]) -> None:
    ws.append([title])
    ws["A1"].font = Font(bold=True, size=13)
    ws.append([company_name])
    ws.append([])
    ws.append(["", columns[0], columns[1]])
    for cell in ws[4]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor="1F4E79")
    for heading, rows in blocks:
        if heading:
            ws.append([heading.upper()])
            ws[ws.max_row][0].font = Font(bold=True)
        for row in rows:
            if row["kind"] == "section":
                ws.append([row["label"]])
                ws[ws.max_row][0].font = Font(bold=True, italic=True)
                continue
            ws.append([("" if row["kind"] == "total" else "   ") + row["label"], float(row["value"]), float(row["previous"])])
            if row["kind"] == "total":
                for cell in ws[ws.max_row]:
                    cell.font = Font(bold=True)
    ws.column_dimensions["A"].width = 78
    for col in "BC":
        ws.column_dimensions[col].width = 20
    for row in ws.iter_rows(min_row=5, min_col=2, max_col=3):
        for cell in row:
            cell.number_format = '#,##0.00;(#,##0.00)'
            cell.alignment = Alignment(horizontal="right")


def statements_excel(data: dict, company_name: str) -> bytes:
    wb = Workbook()
    n = f"{data['date_to'].strftime('%d/%m/%Y')}"
    n1 = f"{data['previous_to'].strftime('%d/%m/%Y')}"
    _sheet(wb.active, f"Balanço em {n}", company_name, (n, n1), [
        ("Activo", data["balance_sheet"]["assets"]),
        ("Capital próprio e passivo", data["balance_sheet"]["equity_liabilities"])])
    wb.active.title = "Balanço"
    period = f"{data['date_from'].strftime('%d/%m/%Y')} a {n}"
    prev_period = f"{data['previous_from'].strftime('%d/%m/%Y')} a {n1}"
    _sheet(wb.create_sheet("Demonstração de resultados"), f"Demonstração de resultados por natureza - {period}",
           company_name, (period, prev_period), [(None, data["income_statement"])])
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()
