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
    assert load_workbook(io.BytesIO(excel_template())).sheetnames == ["Saldos iniciais", "Instruções"]
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
