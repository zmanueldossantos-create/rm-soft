"""
Contabilidade - the journals and the entries: the default journals, drafts, posting (balanced, last-level active
accounts, a period that takes entries, numbered per journal and year without gaps), the estorno, and the chart guarded
(no sub-account under an account with entries, no deletion).
"""
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.services.account_mapping_service import sync_subaccounts
from app.services.chart_of_accounts_service import ChartError, create_account, delete_account, get_chart, start_chart
from app.services.journal_service import (
    JournalError, create_journal, delete_entry, delete_journal, get_entry, list_entries, list_journals, post_entry,
    reverse_entry, save_entry, update_journal,
)


async def _setup(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    chart = await start_chart(db, company_id, "PGC")
    by_code = {a["code"]: a["id"] for a in chart["accounts"]}
    journals = {j["code"]: j["id"] for j in await list_journals(db, company_id)}
    return company_id, by_code, journals


def _lines(by_code, *rows):
    return [{"account_id": by_code[code], "debit": debit, "credit": credit} for code, debit, credit in rows]


@pytest.mark.asyncio
async def test_default_journals_and_their_settings(db, company_with_essentials):
    company_id, by_code, journals = await _setup(db, company_with_essentials)
    assert list(journals) == ["VND", "CMP", "CX", "BCO", "OD", "ABE"]
    await start_chart(db, company_id, "PGC")  # started again: no second set
    assert len(await list_journals(db, company_id)) == 6
    with pytest.raises(JournalError, match="já existe"):
        await create_journal(db, company_id, "od", "Outro")
    extra = await create_journal(db, company_id, "reg", "Regularizações")
    assert extra.code == "REG"
    await update_journal(db, company_id, extra.id, "Regularizações de fim de ano", False)
    with pytest.raises(JournalError, match="inativo"):
        await save_entry(db, company_id, None, entry_id=None, journal_id=extra.id, entry_date=date.today(),
                         description="X", document_ref=None, lines=[])
    await delete_journal(db, company_id, extra.id)
    today = date.today()
    await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                     description="Rascunho", document_ref=None, lines=[])
    with pytest.raises(JournalError, match="tem lançamentos"):
        await delete_journal(db, company_id, journals["OD"])


@pytest.mark.asyncio
async def test_draft_then_post_numbered_per_journal_and_year(db, company_with_essentials):
    company_id, by_code, journals = await _setup(db, company_with_essentials)
    today = date.today()
    # a draft need not balance
    draft = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                             description="Capital social", document_ref="Ata 1",
                             lines=_lines(by_code, ("43.1", "100000", 0)))
    assert (draft.status, draft.number) == ("RASCUNHO", None)
    draft_id = draft.id
    with pytest.raises(JournalError, match="pelo menos duas linhas"):
        await post_entry(db, company_id, None, draft_id)
    with pytest.raises(JournalError, match="não está equilibrado.*diferença 50 000,00"):
        await save_entry(db, company_id, None, entry_id=draft_id, journal_id=journals["OD"], entry_date=today,
                         description="Capital social", document_ref="Ata 1", post=True,
                         lines=_lines(by_code, ("43.1", "100000", 0), ("51", 0, "50000")))
    # refused posting saved nothing: still the one-line draft
    assert (await get_entry(db, company_id, draft_id))["line_count"] == 1
    with pytest.raises(JournalError, match="tem subcontas"):
        await save_entry(db, company_id, None, entry_id=draft_id, journal_id=journals["OD"], entry_date=today,
                         description="Capital social", document_ref=None,
                         lines=_lines(by_code, ("43", "100000", 0)))
    with pytest.raises(JournalError, match="débito ou o crédito, não os dois"):
        await save_entry(db, company_id, None, entry_id=draft_id, journal_id=journals["OD"], entry_date=today,
                         description="Capital social", document_ref=None,
                         lines=_lines(by_code, ("43.1", "10", "10")))
    with pytest.raises(JournalError, match="2 casas decimais"):
        await save_entry(db, company_id, None, entry_id=draft_id, journal_id=journals["OD"], entry_date=today,
                         description="Capital social", document_ref=None,
                         lines=_lines(by_code, ("43.1", "10.005", 0)))
    posted = await save_entry(db, company_id, None, entry_id=draft_id, journal_id=journals["OD"], entry_date=today,
                              description="Capital social", document_ref="Ata 1", post=True,
                              lines=_lines(by_code, ("43.1", "100000", 0), ("51", 0, "100000")))
    assert (posted.status, posted.year, posted.number) == ("LANCADO", today.year, 1)
    with pytest.raises(JournalError, match="não pode ser alterado"):
        await save_entry(db, company_id, None, entry_id=posted.id, journal_id=journals["OD"], entry_date=today,
                         description="Outra", document_ref=None, lines=[])
    with pytest.raises(JournalError, match="não pode ser apagado"):
        await delete_entry(db, company_id, posted.id)

    second = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                              description="Segundo", document_ref=None, post=True,
                              lines=_lines(by_code, ("43.1", "250.50", 0), ("45.1.1", 0, "250.50")))
    other = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["CX"], entry_date=today,
                             description="Primeiro da caixa", document_ref=None, post=True,
                             lines=_lines(by_code, ("45.1.1", "10", 0), ("43.1", 0, "10")))
    assert (second.number, other.number) == (2, 1)
    listed = await list_entries(db, company_id, journal_id=journals["OD"])
    assert [e["label"] for e in listed] == [f"OD {today.year}/0002", f"OD {today.year}/0001"]
    assert listed[0]["debit"] == listed[0]["credit"] == Decimal("250.50")
    assert [e["label"] for e in await list_entries(db, company_id, search="ata 1")] == [f"OD {today.year}/0001"]

    # a draft may be deleted
    gone = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                            description="Engano", document_ref=None, lines=[])
    await delete_entry(db, company_id, gone.id)
    assert len(await list_entries(db, company_id, status="RASCUNHO")) == 0


@pytest.mark.asyncio
async def test_the_periods_that_take_entries(db, company_with_essentials):
    company_id, by_code, journals = await _setup(db, company_with_essentials)
    today = date.today()
    lines = _lines(by_code, ("43.1", "10", 0), ("51", 0, "10"))
    with pytest.raises(JournalError, match=f"ano fiscal {today.year - 1} não existe"):
        await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"],
                         entry_date=date(today.year - 1, 6, 1), description="X", document_ref=None, lines=lines)
    other_month = date(today.year, 1 if today.month != 1 else 2, 1)
    with pytest.raises(JournalError, match="ainda não foi aberto"):
        await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=other_month,
                         description="X", document_ref=None, lines=lines)
    draft = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                             description="X", document_ref=None, lines=lines)
    period = (await db.execute(select(FiscalPeriod).where(FiscalPeriod.company_id == company_id))).scalar_one()
    period.status = "FECHO_PARCIAL"  # the soft-closed month still takes the accountant's late entries
    await db.commit()
    assert (await post_entry(db, company_id, None, draft.id)).number == 1
    period.status = "FECHADO"
    await db.commit()
    with pytest.raises(JournalError, match="fechado definitivamente"):
        await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                         description="X", document_ref=None, lines=lines)
    year = (await db.execute(select(FiscalYear).where(FiscalYear.company_id == company_id))).scalar_one()
    assert year.status == "ABERTO"


@pytest.mark.asyncio
async def test_the_estorno(db, company_with_essentials):
    company_id, by_code, journals = await _setup(db, company_with_essentials)
    today = date.today()
    entry = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["BCO"], entry_date=today,
                             description="Depósito", document_ref="Talão 7", post=True,
                             lines=_lines(by_code, ("43.1", "5000", 0), ("45.1.1", 0, "5000")))
    reversal = await reverse_entry(db, company_id, None, entry.id, today)
    detail = await get_entry(db, company_id, reversal.id)
    assert detail["label"] == f"BCO {today.year}/0002" and detail["description"] == f"Estorno de BCO {today.year}/0001"
    assert [(l["account_code"], l["debit"], l["credit"]) for l in detail["lines"]] == [
        ("43.1", Decimal("0.00"), Decimal("5000.00")), ("45.1.1", Decimal("5000.00"), Decimal("0.00"))]
    assert detail["reversal_of"] == f"BCO {today.year}/0001"
    assert (await get_entry(db, company_id, entry.id))["reversed_by"] == f"BCO {today.year}/0002"
    with pytest.raises(JournalError, match="já foi estornado"):
        await reverse_entry(db, company_id, None, entry.id, today)
    with pytest.raises(JournalError, match="é um estorno"):
        await reverse_entry(db, company_id, None, reversal.id, today)
    draft = await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                             description="R", document_ref=None, lines=[])
    with pytest.raises(JournalError, match="um rascunho apaga-se"):
        await reverse_entry(db, company_id, None, draft.id, today)


@pytest.mark.asyncio
async def test_the_chart_is_guarded_by_the_entries(db, company_with_essentials):
    company_id, by_code, journals = await _setup(db, company_with_essentials)
    today = date.today()
    await create_account(db, company_id, "45.1.9", "Caixa de testes")
    chart = {a["code"]: a for a in (await get_chart(db, company_id))["accounts"]}
    await save_entry(db, company_id, None, entry_id=None, journal_id=journals["OD"], entry_date=today,
                     description="X", document_ref=None, post=True,
                     lines=[{"account_id": chart["45.1.9"]["id"], "debit": 1, "credit": 0},
                            {"account_id": by_code["51"], "debit": 0, "credit": 1}])
    with pytest.raises(ChartError, match="já tem lançamentos - não pode ter subcontas"):
        await create_account(db, company_id, "45.1.9.1", "Sub")
    with pytest.raises(ChartError, match="tem lançamentos - não pode ser apagada"):
        await delete_account(db, company_id, chart["45.1.9"]["id"])
    assert {a["code"]: a for a in (await get_chart(db, company_id))["accounts"]}["45.1.9"]["in_use"] == "tem lançamentos"
    result = await sync_subaccounts(db, company_id)  # nothing to make, nothing refused
    assert result["created"] == 0
