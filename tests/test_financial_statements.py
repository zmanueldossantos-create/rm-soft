"""
Contabilidade - the Balanço and the Demonstração de resultados of the PGC: a customer that owes is an asset, one that
paid in advance a liability; the result of the year in the equity before the closing; the Balanço balances; the
column N-1; Excel and PDF.
"""
from datetime import date
from decimal import Decimal

import pytest

from app.services.chart_of_accounts_service import start_chart
from app.services.financial_statements_service import StatementError, financial_statements, statements_excel
from app.services.journal_service import list_journals, save_entry
from app.utils.accounting_pdf import generate_statements_pdf


@pytest.mark.asyncio
async def test_the_balance_sheet_and_the_income_statement(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    chart = await start_chart(db, company_id, "PGC")
    code = {a["code"]: a["id"] for a in chart["accounts"]}
    od = next(j["id"] for j in await list_journals(db, company_id) if j["code"] == "OD")
    today = date.today()

    async def entry(*lines):
        await save_entry(db, company_id, None, entry_id=None, journal_id=od, entry_date=today, description="Teste",
                         document_ref=None, post=True,
                         lines=[{"account_id": code[c], "debit": d, "credit": cr} for c, d, cr in lines])

    await entry(("43.1", 1_000_000, 0), ("51", 0, 1_000_000))  # the capital, into the bank
    await entry(("31.1.2.1.1", 114_000, 0), ("61.3.1", 0, 100_000), ("34.5.3", 0, 14_000))  # a sale on credit
    await entry(("45.1.1", 5_000, 0), ("31.9.1", 0, 5_000))  # a customer's advance: a liability
    await entry(("75.2", 20_000, 0), ("43.1", 0, 20_000))  # a service paid

    data = await financial_statements(db, company_id, today.replace(month=1, day=1), today)
    assets = {r["key"]: r["value"] for r in data["balance_sheet"]["assets"]}
    other = {r["key"]: r["value"] for r in data["balance_sheet"]["equity_liabilities"]}
    assert (assets["A_RECEBER"], assets["A_DISP"], assets["T_ACTIVO"]) == (Decimal(114_000), Decimal(985_000), Decimal(1_099_000))
    assert (other["C_CAPITAL"], other["C_RESULTADO"], other["T_CP"]) == (Decimal(1_000_000), Decimal(80_000), Decimal(1_080_000))
    assert other["P_PAGAR"] == Decimal(19_000)  # the VAT owed and the customer's advance
    assert other["T_CP_PASSIVO"] == assets["T_ACTIVO"] and data["balance_sheet"]["balanced"]
    assert data["balance_sheet"]["unclassified"] == []
    assert all(r["previous"] in (None, 0) for r in data["balance_sheet"]["assets"])  # N-1: nothing a year ago

    income = {r["key"]: r["value"] for r in data["income_statement"]}
    assert (income["R_VENDAS"], income["R_OUTROS_CUSTOS"]) == (Decimal(100_000), Decimal(-20_000))  # a cost: a negative
    assert income["T_OPERACIONAIS"] == income["T_LIQUIDO"] == Decimal(80_000) == other["C_RESULTADO"]

    with pytest.raises(StatementError):
        await financial_statements(db, company_id, today, today.replace(year=today.year - 1))
    company = {"name": "MEL DA ROCHA - COMÉRCIO GERAL E PRESTAÇÃO DE SERVIÇOS, LDA", "nif": "5000000000",
               "address": "Rua da Brigada Eletrónica, Palanca – Kilamba Kiaxi, Luanda", "phone_number": "+244921717712"}
    pypdf = pytest.importorskip("pypdf")
    import io
    # the balance sheet holds on one page, its last total included (a company box of two lines, as a real one)
    assert len(pypdf.PdfReader(io.BytesIO(generate_statements_pdf(data, company, "balance"))).pages) == 1
    assert statements_excel(data, "Empresa")[:2] == b"PK"
    for which in ("balance", "income", "both"):
        assert generate_statements_pdf(data, company, which).startswith(b"%PDF")
