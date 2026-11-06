"""
Contabilidade - the chart of accounts: the PGC loaded, the Excel model and its import (all or nothing, every wrong row
listed), one account at a time (its parent first, its code never changes, no deletion with sub-accounts).
"""
import io

import pytest
from openpyxl import Workbook, load_workbook

from app.services.chart_of_accounts_service import (
    ChartError, ChartImportError, create_account, delete_account, excel_template, get_chart, import_chart,
    parent_code, sort_key, start_chart, update_account,
)


def _xlsx(rows) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "Plano de contas"
    ws.append(("Código", "Descrição"))
    for row in rows:
        ws.append(row)
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def test_codes():
    assert [parent_code(c) for c in ("4", "45", "45.1", "45.1.10")] == [None, "4", "45", "45.1"]
    assert sorted(["45.10", "45.2", "45", "4", "43"], key=sort_key) == ["4", "43", "45", "45.2", "45.10"]


@pytest.mark.asyncio
async def test_the_pgc_then_an_account_at_a_time(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    chart = await start_chart(db, company_id, "PGC")
    codes = [a["code"] for a in chart["accounts"]]
    assert chart["source"] == "PGC" and codes[:3] == ["1", "11", "11.1"] and "34.5.3" in codes and "61.3" in codes
    with pytest.raises(ChartError, match="Crie primeiro a conta 47"):
        await create_account(db, company_id, "47.1", "Sem mãe")
    caixa = next(a for a in chart["accounts"] if a["code"] == "45.1")
    sub = await create_account(db, company_id, "45.1.1", "Caixa sede")
    assert (sub.level, sub.parent_id) == (4, caixa["id"])
    with pytest.raises(ChartError, match="já existe"):
        await create_account(db, company_id, "45", "Outra")
    caixa = next(a for a in chart["accounts"] if a["code"] == "45")
    with pytest.raises(ChartError, match="inválido"):
        await create_account(db, company_id, "450", "Três algarismos")
    with pytest.raises(ChartError, match="tem subcontas"):
        await delete_account(db, company_id, caixa["id"])
    await update_account(db, company_id, sub.id, "Caixa da sede", False)
    await delete_account(db, company_id, sub.id)
    again = await start_chart(db, company_id, "PGC")  # loaded again: nothing removed, nothing renamed
    assert len(again["accounts"]) == len(chart["accounts"])


@pytest.mark.asyncio
async def test_the_excel_import(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    model = load_workbook(io.BytesIO(excel_template()))
    assert [c.value for c in model["Plano de contas"][1]] == ["Código", "Descrição"]

    with pytest.raises(ChartImportError) as wrong:
        await import_chart(db, company_id, _xlsx([("4", "Meios monetários"), ("43.1", "Sem mãe"), ("45", None),
                                                  ("4", "Repetida")]))
    assert len(wrong.value.errors) == 3 and (await get_chart(db, company_id))["accounts"] == []  # nothing saved

    result = await import_chart(db, company_id, _xlsx([("45.1", "Caixa sede"), ("4", "Meios monetários"),
                                                       (45, "Caixa"), ("45.10", "Caixa 10")]))
    assert result == {"created": 4, "renamed": 0, "unchanged": 0}
    chart = await get_chart(db, company_id)
    assert chart["source"] == "PROPRIO" and [a["code"] for a in chart["accounts"]] == ["4", "45", "45.1", "45.10"]
    result = await import_chart(db, company_id, _xlsx([("45", "Caixa geral"), ("45.1", "Caixa sede")]))
    assert result == {"created": 0, "renamed": 1, "unchanged": 1}


def test_the_pgc_reference_list_is_consistent():
    """Every code of the PGC list is valid, appears once, and has its parent in the list."""
    from app.data.pgc_angola import PGC_ACCOUNTS
    from app.services.chart_of_accounts_service import check_code
    codes = [code for code, _ in PGC_ACCOUNTS]
    assert len(codes) == len(set(codes))
    for code, name in PGC_ACCOUNTS:
        check_code(code)
        assert name.strip()
        parent = parent_code(code)
        assert parent is None or parent in codes, code
    assert {c for c in codes if len(c) == 1} == {"1", "2", "3", "4", "5", "6", "7", "8"}
