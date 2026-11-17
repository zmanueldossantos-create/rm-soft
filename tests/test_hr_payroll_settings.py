"""Recursos Humanos, step 2: the payroll settings - the formulas (parsed, never eval), the IRT table and its brackets,
the rubricas (codes, formulas reading other rubricas, loops refused, exempt limit) and the payslip simulation that
reads them all."""
from datetime import date

import pytest

from app.services.employee_service import EmployeeError, create_employee
from app.services.payroll_formula import FormulaError, evaluate, parse
from app.services.payroll_settings_service import (
    DEFAULT_IRT_TABLE, check_formula, create_item, delete_item, employee_items, get_payroll_settings, irt_of,
    list_irt_tables, list_items, save_irt_table, set_employee_items, simulate_payslip, update_item, update_payroll_settings,
)

IBAN = "AO06004000000123456789027"


def test_the_formulas():
    ctx = {"SB": 200000, "VH": 1000, "HE50": 4, "ANTIGUIDADE": 6, "SUB": 45000}
    assert evaluate(parse("SB * 10%"), ctx) == 20000
    assert evaluate(parse("vh * 1,5 * HE50"), ctx) == 6000  # case and decimal comma
    assert evaluate(parse("SE(ANTIGUIDADE >= 5; SB * 5%; 0)"), ctx) == 10000
    assert evaluate(parse("MIN(SUB; 30000) + MAX(0; -5)"), ctx) == 30000
    assert evaluate(parse("ARRED(10 / 3)"), ctx) == 3.33
    assert evaluate(parse("-SB + 2 * (3 + 4)"), ctx) == -199986
    assert evaluate(parse("SB / 0"), ctx) == 0  # never breaks a payslip
    for bad, message in (("SB *", "incompleta"), ("SB $ 2", "Carácter inesperado"), ("FOO(1)", "Função desconhecida"),
                         ("SE(1; 2)", "3 argumento"), ("SB 2", "Sobra"), ("", "Escreva")):
        with pytest.raises(FormulaError, match=message):
            parse(bad)
    with pytest.raises(FormulaError, match="desconhecida: X"):
        evaluate(parse("X + 1"), ctx)


def test_the_irt_brackets():
    brackets = DEFAULT_IRT_TABLE["brackets"]
    assert irt_of(150000, brackets) == 0  # exempt up to 150 000
    assert irt_of(182800, brackets) == 17748  # 12 500 + 32 800 x 16 %
    assert irt_of(12000000, brackets) == 2842250  # 2 342 250 + 2 000 000 x 25 %


@pytest.mark.asyncio
async def test_the_settings_and_the_irt_tables(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    assert (await get_payroll_settings(db, company_id))["inss_employee_rate"] == 3.0
    changed = await update_payroll_settings(db, company_id, {"inss_employee_rate": 3, "inss_employer_rate": 8,
                                                             "monthly_hours": 176, "monthly_days": 22, "inss_deducted_from_irt": True})
    assert changed["monthly_hours"] == 176.0
    with pytest.raises(EmployeeError, match="Horas por mês"):
        await update_payroll_settings(db, company_id, {**changed, "monthly_hours": 0})

    tables = await list_irt_tables(db, company_id)
    assert len(tables) == 1 and tables[0]["in_force"] and len(tables[0]["brackets"]) == 11
    new = [{"from": 0, "to": 200000, "fixed": 0, "rate": 0}, {"from": 200000, "to": None, "fixed": 0, "rate": 20}]
    future = await save_irt_table(db, company_id, None, {"name": "IRPS 2027", "valid_from": date(2027, 1, 1), "brackets": new})
    assert future["brackets"][1]["over"] == 200000  # «applied above» defaults to the bracket's start
    tables = await list_irt_tables(db, company_id)
    assert [t["name"] for t in tables] == ["IRPS 2027", DEFAULT_IRT_TABLE["name"]] and not tables[0]["in_force"]
    for brackets, message in (([{"from": 100, "to": None, "rate": 1}], "começa em 0"),
                              ([{"from": 0, "to": 100, "rate": 0}, {"from": 150, "to": None, "rate": 1}], "acabar onde começa"),
                              ([{"from": 0, "to": 100, "rate": 0}], "último escalão")):
        with pytest.raises(EmployeeError, match=message):
            await save_irt_table(db, company_id, None, {"name": "X", "valid_from": date(2028, 1, 1), "brackets": brackets})
    with pytest.raises(EmployeeError, match="Já existe uma tabela"):
        await save_irt_table(db, company_id, None, {"name": "Y", "valid_from": date(2027, 1, 1), "brackets": new})


@pytest.mark.asyncio
async def test_the_rubricas(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    items = (await list_items(db, company_id))["items"]
    codes = [i["code"] for i in items]
    assert codes[:2] == ["SUB_ALIM", "SUB_TRANSP"] and "FALTAS" in codes
    assert next(i for i in items if i["code"] == "SUB_TRANSP")["irt_exempt_limit"] == 30000

    base = {"name": "Bónus de antiguidade", "nature": "ABONO", "calc_method": "FORMULA", "subject_inss": True, "subject_irt": True}
    bonus = await create_item(db, company_id, {**base, "code": "bonus_ant", "formula": "SE(ANTIGUIDADE >= 2; SB * 5%; 0)",
                                               "applies_to_all": True})
    assert bonus["code"] == "BONUS_ANT"
    assert (await check_formula(db, company_id, "BONUS_ANT * 2"))["value"] == 10000  # example: SB 100 000, 5 years
    for data, message in (
        ({"code": "SB"}, "reservado"), ({"code": "1X"}, "Código"), ({"code": "SUB_ALIM"}, "Já existe"),
        ({"code": "B2", "formula": "FOO + 1"}, "variável desconhecida FOO"),
        ({"code": "B2", "formula": "B2 + 1"}, "própria rubrica"),
        ({"code": "B2", "formula": "SB *"}, "Fórmula"),
    ):
        with pytest.raises(EmployeeError, match=message):
            await create_item(db, company_id, {**base, "formula": "SB", **data})
    double = await create_item(db, company_id, {**base, "code": "DOBRO", "formula": "BONUS_ANT * 2"})
    with pytest.raises(EmployeeError, match="ciclo"):
        await update_item(db, company_id, bonus["id"], {**base, "code": "BONUS_ANT", "formula": "DOBRO + 1", "applies_to_all": True})
    with pytest.raises(EmployeeError, match="usado na fórmula de DOBRO"):
        await update_item(db, company_id, bonus["id"], {**base, "code": "BONUS_X", "formula": "SB", "applies_to_all": True})
    with pytest.raises(EmployeeError, match="usado na fórmula de DOBRO"):
        await delete_item(db, company_id, bonus["id"])
    await delete_item(db, company_id, double["id"])
    await delete_item(db, company_id, bonus["id"])


@pytest.mark.asyncio
async def test_the_payslip_simulation(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    maria = await create_employee(db, company_id, user_id, {"full_name": "Maria Lopes", "hired_on": date(2024, 3, 1),
                                                            "base_salary": 180000, "payment_method": "TRANSFERENCIA", "iban": IBAN})
    items = {i["code"]: i for i in (await list_items(db, company_id))["items"]}
    with pytest.raises(EmployeeError, match="indique o valor"):
        await set_employee_items(db, company_id, maria["id"], [{"item_id": items["SUB_ALIM"]["id"]}])
    with pytest.raises(EmployeeError, match="em cada mês"):
        await set_employee_items(db, company_id, maria["id"], [{"item_id": items["PREMIO"]["id"]}])
    given = await set_employee_items(db, company_id, maria["id"], [{"item_id": items["SUB_TRANSP"]["id"], "amount": 40000},
                                                                   {"item_id": items["SUB_ALIM"]["id"], "amount": 20000}])
    assert {g["code"]: g["amount"] for g in given} == {"SUB_TRANSP": 40000.0, "SUB_ALIM": 20000.0}

    slip = await simulate_payslip(db, company_id, maria["id"], day=date(2026, 11, 17))
    # gross 240 000; INSS 3 % of 240 000; IRT on 180 000 + 10 000 above the transport's exempt 30 000 - INSS
    assert (slip["gross"], slip["inss_base"], slip["inss_employee"], slip["inss_employer"]) == (240000, 240000, 7200, 19200)
    assert (slip["irt_base"], slip["irt"], slip["net"]) == (182800, 17748, 215052)
    assert {line["code"]: line["irt_taxed"] for line in slip["allowances"]} == {"SUB_ALIM": 0, "SUB_TRANSP": 10000}

    # a rubrica for everybody, by formula; a month's absence that reduces both bases
    await create_item(db, company_id, {"code": "BONUS_ANT", "name": "Bónus", "nature": "ABONO", "calc_method": "FORMULA",
                                       "formula": "SE(ANTIGUIDADE >= 2; SB * 5%; 0)", "applies_to_all": True,
                                       "subject_inss": True, "subject_irt": True})
    slip = await simulate_payslip(db, company_id, maria["id"], {"faltas": 6000}, day=date(2026, 11, 17))
    assert {line["code"]: line["value"] for line in slip["allowances"]}["BONUS_ANT"] == 9000
    assert slip["gross"] == 249000 and slip["inss_base"] == 243000  # 249 000 - 6 000 of absences
    assert slip["deductions"][0]["code"] == "FALTAS"
    assert slip["net"] == round(slip["gross"] - slip["inss_employee"] - slip["irt"] - 6000, 2)

    await set_employee_items(db, company_id, maria["id"], [])
    assert await employee_items(db, company_id, maria["id"]) == []
