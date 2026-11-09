"""
Contabilidade - the closing of the year: the apuramento (the classes 6 and 7 into 82 to 86, then 82 to 87 into the net
result 88.1, made by the system), refused with a draft in the year; the Demonstração de resultados unchanged by it;
the abertura of the next year (88.1 into 81 Resultados transitados); the cancellations in their order.
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.journal import JournalEntry
from app.services.chart_of_accounts_service import start_chart
from app.services.financial_statements_service import financial_statements
from app.services.journal_service import JournalError, delete_entry, get_entry, list_journals, reverse_entry, save_entry
from app.services.year_closing_service import (
    CLOSING, OPENING, YearClosingError, cancel, close_year, open_next_year, year_status,
)


async def _lines(db, company_id, entry_id):
    entry = await get_entry(db, company_id, entry_id)
    return sorted((l["account_code"], float(l["debit"]), float(l["credit"])) for l in entry["lines"])


@pytest.mark.asyncio
async def test_the_closing_and_the_opening(db, company_with_essentials):
    ctx = company_with_essentials
    company_id = ctx["company"].id
    today = date.today()
    year = today.year
    # December of this year and January of the next one open (the fixture opens the current month)
    this_year = (await db.execute(select(FiscalYear).where(FiscalYear.company_id == company_id))).scalar_one()
    if today.month != 12:
        db.add(FiscalPeriod(company_id=company_id, fiscal_year_id=this_year.id, month=12, status="ABERTO"))
    next_year = FiscalYear(company_id=company_id, year=year + 1, status="ABERTO")
    db.add(next_year)
    await db.flush()
    db.add(FiscalPeriod(company_id=company_id, fiscal_year_id=next_year.id, month=1, status="ABERTO"))
    await db.commit()

    chart = await start_chart(db, company_id, "PGC")
    code = {a["code"]: a["id"] for a in chart["accounts"]}
    od = next(j["id"] for j in await list_journals(db, company_id) if j["code"] == "OD")

    async def entry(*lines, post=True):
        return await save_entry(db, company_id, None, entry_id=None, journal_id=od, entry_date=today, description="Teste",
                                document_ref=None, post=post,
                                lines=[{"account_id": code[c], "debit": d, "credit": cr} for c, d, cr in lines])

    await entry(("31.1.2.1.1", 114_000, 0), ("61.3.1", 0, 100_000), ("34.5.3", 0, 14_000))
    await entry(("75.2", 20_000, 0), ("43.1", 0, 20_000))
    await entry(("87.1", 10_000, 0), ("34.1", 0, 10_000))  # the tax on the profit
    draft = await entry(("75.2", 1, 0), post=False)
    draft_id = draft.id

    status = await year_status(db, company_id, year)
    assert status["result"] == Decimal(70_000) and not status["can_close"]
    with pytest.raises(YearClosingError, match="rascunho"):
        await close_year(db, company_id, None, year)
    await delete_entry(db, company_id, draft_id)

    closing = await close_year(db, company_id, None, year)
    closing_id = closing.id
    assert (closing.entry_date, closing.source_kind) == (date(year, 12, 31), CLOSING)
    assert await _lines(db, company_id, closing_id) == sorted([
        ("61.3.1", 100_000.0, 0.0), ("75.2", 0.0, 20_000.0),       # the classes 6 and 7 closed
        ("82.1", 0.0, 100_000.0), ("82.9", 20_000.0, 0.0),         # into the operating results
        ("82.19", 80_000.0, 0.0), ("87.9", 0.0, 10_000.0),         # 82 and 87 moved out
        ("88.1", 0.0, 70_000.0),                                   # into the net result (a profit: credor)
    ])
    end = date(year, 12, 31)
    data = await financial_statements(db, company_id, date(year, 1, 1), end)
    assert next(r["value"] for r in data["income_statement"] if r["key"] == "T_LIQUIDO") == Decimal(70_000)  # unchanged
    assert next(r["value"] for r in data["balance_sheet"]["equity_liabilities"] if r["key"] == "C_RESULTADO") == Decimal(70_000)
    with pytest.raises(JournalError, match="Fecho do exercício"):  # never from the Lançamentos screen
        await reverse_entry(db, company_id, None, closing_id, end)
    with pytest.raises(YearClosingError, match="já está apurado"):
        await close_year(db, company_id, None, year)

    opening = await open_next_year(db, company_id, None, year)
    assert opening.source_kind == OPENING
    assert await _lines(db, company_id, opening.id) == sorted([("88.1", 70_000.0, 0.0), ("81", 0.0, 70_000.0)])
    data = await financial_statements(db, company_id, date(year + 1, 1, 1), date(year + 1, 1, 1))
    equity = {r["key"]: r["value"] for r in data["balance_sheet"]["equity_liabilities"]}
    assert (equity["C_TRANSITADOS"], equity["C_RESULTADO"]) == (Decimal(70_000), Decimal(0))

    with pytest.raises(YearClosingError, match="Anule primeiro a abertura"):
        await cancel(db, company_id, None, year, CLOSING)
    await cancel(db, company_id, None, year, OPENING)
    await cancel(db, company_id, None, year, CLOSING)
    status = await year_status(db, company_id, year)
    assert status["closing"] is None and status["opening"] is None and status["can_close"]
    estornos = (await db.execute(select(JournalEntry.source_kind).where(JournalEntry.reversal_of_id.is_not(None)))).scalars().all()
    assert sorted(estornos) == [CLOSING, OPENING]  # they keep their kind: out of the Demonstração de resultados
    assert next(r["value"] for r in (await financial_statements(db, company_id, date(year, 1, 1), end))["income_statement"]
                if r["key"] == "T_LIQUIDO") == Decimal(70_000)
    assert (await close_year(db, company_id, None, year)).source_kind == CLOSING  # closed again
