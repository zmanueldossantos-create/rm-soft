"""
Contabilidade - the balancete (balance before the period, its debits and credits, the balance at its end; an account
adds up its sub-accounts, the classes make the totals; the drafts never count) and the extrato de conta.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.accounting_reports_service import ReportError, account_ledger, trial_balance, trial_balance_excel
from app.services.chart_of_accounts_service import start_chart
from app.services.journal_service import list_journals, save_entry
from app.utils.accounting_pdf import generate_account_ledger_pdf, generate_trial_balance_pdf


@pytest.mark.asyncio
async def test_the_trial_balance_and_the_ledger(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    chart = await start_chart(db, company_id, "PGC")
    code = {a["code"]: a["id"] for a in chart["accounts"]}
    od = next(j["id"] for j in await list_journals(db, company_id) if j["code"] == "OD")
    today = date.today()
    day1, day2 = today.replace(day=1), today.replace(day=2)

    async def entry(day, lines, post=True):
        await save_entry(db, company_id, None, entry_id=None, journal_id=od, entry_date=day, description="Teste",
                         document_ref=None, post=post,
                         lines=[{"account_id": code[c], "debit": d, "credit": cr} for c, d, cr in lines])

    await entry(day1, [("45.1.1", 1000, 0), ("51", 0, 1000)])  # before the period
    await entry(day2, [("43.1", 300, 0), ("45.1.1", 0, 300)])
    await entry(day2, [("45.1.1", 999, 0), ("51", 0, 999)], post=False)  # a draft: never counted

    data = await trial_balance(db, company_id, day2, day2)
    rows = {r["code"]: (r["opening"], r["debit"], r["credit"], r["closing"]) for r in data["accounts"]}
    assert rows["45.1.1"] == rows["45.1"] == rows["45"] == (Decimal(1000), Decimal(0), Decimal(300), Decimal(700))
    assert rows["4"] == (Decimal(1000), Decimal(300), Decimal(300), Decimal(1000))  # 45 and 43 together
    assert rows["51"] == rows["5"] == (Decimal(-1000), Decimal(0), Decimal(0), Decimal(-1000))  # credor
    assert "61" not in rows  # no movement, no balance: left out
    assert data["totals"] == {"opening": 0, "debit": 300, "credit": 300, "closing": 0}
    assert [r["code"] for r in (await trial_balance(db, company_id, day2, day2, max_level=1))["accounts"]] == ["4", "5"]
    assert len((await trial_balance(db, company_id, day2, day2, all_accounts=True))["accounts"]) == len(chart["accounts"])
    with pytest.raises(ReportError):
        await trial_balance(db, company_id, day2, day1)

    ledger = await account_ledger(db, company_id, code["45"], day2, day2)  # 45 and its sub-accounts
    assert (ledger["opening"], ledger["closing"]) == (Decimal(1000), Decimal(700))
    [line] = ledger["lines"]
    assert (line["account_code"], line["credit"], line["balance"], line["entry"]) == ("45.1.1", Decimal(300), Decimal(700), f"OD {today.year}/0002")

    company = {"name": "Empresa", "nif": "5000000000"}
    assert trial_balance_excel(data, "Empresa")[:2] == b"PK"
    assert generate_trial_balance_pdf(data, company).startswith(b"%PDF")
    assert generate_account_ledger_pdf(ledger, company).startswith(b"%PDF")


@pytest.mark.asyncio
async def test_the_razao_and_the_diario(db, company_with_essentials):
    """The razão: every last-level account of the range with a balance or a movement, each with its lines; a bound
    covers its sub-accounts. The diário: the posted entries of the period with their lines (one journal, or all)."""
    from app.services.accounting_reports_service import general_ledger, general_ledger_excel, journal_book, journal_book_excel
    from app.utils.accounting_pdf import generate_general_ledger_pdf, generate_journal_book_pdf
    company_id = company_with_essentials["company"].id
    chart = await start_chart(db, company_id, "PGC")
    code = {a["code"]: a["id"] for a in chart["accounts"]}
    journals = {j["code"]: j["id"] for j in await list_journals(db, company_id)}
    today = date.today()
    day1, day2 = today.replace(day=1), today.replace(day=2)

    async def entry(journal, day, lines, post=True):
        await save_entry(db, company_id, None, entry_id=None, journal_id=journals[journal], entry_date=day,
                         description="Teste", document_ref="DOC1", post=post,
                         lines=[{"account_id": code[c], "debit": d, "credit": cr} for c, d, cr in lines])

    await entry("ABE", day1, [("45.1.1", 1000, 0), ("51", 0, 1000)])  # before the period
    await entry("OD", day2, [("43.1", 300, 0), ("45.1.1", 0, 300)])
    await entry("OD", day2, [("45.1.1", 999, 0), ("51", 0, 999)], post=False)  # a draft: never counted

    data = await general_ledger(db, company_id, day2, day2)
    accounts = {a["code"]: a for a in data["accounts"]}
    assert list(accounts) == ["43.1", "45.1.1", "51"]  # the chart's order; 51 only an opening balance
    assert (accounts["45.1.1"]["opening"], accounts["45.1.1"]["closing"]) == (Decimal(1000), Decimal(700))
    assert accounts["51"]["lines"] == [] and accounts["51"]["closing"] == Decimal(-1000)
    assert (data["total_debit"], data["total_credit"]) == (Decimal(300), Decimal(300))
    assert [a["code"] for a in (await general_ledger(db, company_id, day2, day2, "4", "45"))["accounts"]] == ["43.1", "45.1.1"]
    assert [a["code"] for a in (await general_ledger(db, company_id, day2, day2, "5"))["accounts"]] == ["51"]
    with pytest.raises(ReportError):
        await general_ledger(db, company_id, day2, day2, "5", "4")

    book = await journal_book(db, company_id, day1, day2)
    assert [e["label"] for e in book["entries"]] == [f"ABE {today.year}/0001", f"OD {today.year}/0001"]
    assert book["total"] == Decimal(1300) and len(book["entries"][1]["lines"]) == 2
    only_od = await journal_book(db, company_id, day1, day2, journals["OD"])
    assert len(only_od["entries"]) == 1 and only_od["journal"].startswith("OD")

    company = {"name": "Empresa", "nif": "5000000000"}
    assert general_ledger_excel(data, "Empresa")[:2] == b"PK" and journal_book_excel(book, "Empresa")[:2] == b"PK"
    assert generate_general_ledger_pdf(data, company).startswith(b"%PDF")
    assert generate_journal_book_pdf(book, company).startswith(b"%PDF")
