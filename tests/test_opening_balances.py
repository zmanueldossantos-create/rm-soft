"""
Contabilidade - the opening balances imported from the Excel model: all or nothing with every wrong row listed (an
account that does not exist, one with sub-accounts, the totals not equal); one entry in ABE; a new import cancels the
previous one; never cancelled from the Lançamentos screen.
"""
import io
from datetime import date
from decimal import Decimal

import pytest
from openpyxl import Workbook, load_workbook

from app.services.chart_of_accounts_service import start_chart
from app.services.journal_service import JournalError, reverse_entry
from app.services.opening_balances_service import (
    OpeningBalancesError, cancel_opening_balances, excel_template, import_opening_balances, opening_balances,
)


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Saldos iniciais"
    ws.append(("Código", "Descrição", "Débito", "Crédito"))
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


@pytest.mark.asyncio
async def test_the_import_of_the_opening_balances(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    today = date.today()
    assert load_workbook(io.BytesIO(await excel_template(db, company_id))).sheetnames == ["Saldos iniciais", "Instruções"]
    with pytest.raises(OpeningBalancesError, match="plano de contas"):
        await import_opening_balances(db, company_id, None, _xlsx([("43.1", "", 10, None)]), today)
    await start_chart(db, company_id, "PGC")

    with pytest.raises(OpeningBalancesError) as refused:
        await import_opening_balances(db, company_id, None, _xlsx([
            ("47.9", "Não existe", 10, None), ("43", "Tem subcontas", 10, None), ("43.1", "Banco", 100, 5),
            ("51", "Capital", None, 50),
        ]), today)
    errors = refused.value.errors
    assert any("47.9 não existe" in e for e in errors) and any("43 tem subcontas" in e for e in errors)
    assert any("não os dois" in e for e in errors) and any("diferença" in e for e in errors)
    assert (await opening_balances(db, company_id))["entry"] is None  # nothing imported

    await import_opening_balances(db, company_id, None, _xlsx([
        ("43.1", "Banco", 2_500_000, None), ("45.1.1", "Caixa", "150 000,50", None),
        ("51", "Capital", None, 2_000_000), ("81", "Resultados transitados", None, 650_000.50),
    ]), today)
    status = await opening_balances(db, company_id)
    assert status["entry"]["label"] == f"ABE {today.year}/0001" and status["entry"]["total"] == Decimal("2650000.50")
    assert [l["code"] for l in status["entry"]["lines"]] == ["43.1", "45.1.1", "51", "81"]
    with pytest.raises(JournalError, match="Saldos iniciais"):  # never from the Lançamentos screen
        await reverse_entry(db, company_id, None, status["entry"]["id"], today)

    # a corrected file: the import before is cancelled, the new one posted
    await import_opening_balances(db, company_id, None, _xlsx([("43.1", "", 1_000, None), ("51", "", None, 1_000)]), today)
    status = await opening_balances(db, company_id)
    assert status["entry"]["label"] == f"ABE {today.year}/0003" and status["entry"]["total"] == Decimal(1_000)  # 0002: the estorno

    await cancel_opening_balances(db, company_id, None)
    assert (await opening_balances(db, company_id))["entry"] is None
    with pytest.raises(OpeningBalancesError, match="Não há saldos"):
        await cancel_opening_balances(db, company_id, None)


@pytest.mark.asyncio
async def test_a_bank_row_is_also_its_opening_balance_in_tesouraria(db, company_with_essentials):
    """Typed once: the bank account's sub-account in the import sets its Tesouraria opening balance; cancelled, it goes
    back to «por definir» - unless the company changed it in Tesouraria since."""
    from app.models.bank import Bank
    from app.models.company_bank_account import CompanyBankAccount
    from app.models.currency import Currency
    from app.services.account_mapping_service import sync_subaccounts
    from app.services.bank_treasury_service import list_bank_positions, set_opening_balance
    company_id = company_with_essentials["company"].id
    today = date.today()
    bank, kz = Bank(acronym="BAI", full_name="BAI"), Currency(code="AOA", name="Kwanza")
    db.add_all([bank, kz])
    await db.flush()
    account = CompanyBankAccount(company_id=company_id, bank_id=bank.id, account_number="0001", iban="AO060001", currency_id=kz.id)
    db.add(account)
    await db.commit()
    account_id = account.id
    await start_chart(db, company_id, "PGC")
    await sync_subaccounts(db, company_id)  # BAI -> 43.1.1
    # the model lists the company's banks, tills and the capital, amounts empty (nothing posted if imported unchanged)
    sheet = load_workbook(io.BytesIO(await excel_template(db, company_id)))["Saldos iniciais"]
    rows = [r for r in sheet.iter_rows(min_row=2, values_only=True) if r[0]]
    assert ("43.1.1", "BAI · 0001", None, None) in rows and rows[-1][0] == "51" and all(r[2] is None for r in rows)
    with pytest.raises(OpeningBalancesError, match="não tem saldos"):
        out = io.BytesIO()
        sheet.parent.save(out)
        await import_opening_balances(db, company_id, None, out.getvalue(), today)

    await import_opening_balances(db, company_id, None, _xlsx([("43.1.1", "BAI", 500_000, None), ("51", "", None, 500_000)]), today)
    [position] = await list_bank_positions(db, company_id)
    assert position["opening_balance"] == 500_000 and position["opening_date"] == today and position["opening_from_accounting"]

    await cancel_opening_balances(db, company_id, None)
    [position] = await list_bank_positions(db, company_id)
    assert position["opening_balance"] == 0 and position["opening_date"] is None  # «por definir» again

    await import_opening_balances(db, company_id, None, _xlsx([("43.1.1", "BAI", 300_000, None), ("51", "", None, 300_000)]), today)
    await set_opening_balance(db, company_id, account_id, 310_000, today)  # the company's own, in Tesouraria
    [position] = await list_bank_positions(db, company_id)
    assert not position["opening_from_accounting"]
    await cancel_opening_balances(db, company_id, None)
    [position] = await list_bank_positions(db, company_id)
    assert position["opening_balance"] == 310_000  # kept: changed there since
