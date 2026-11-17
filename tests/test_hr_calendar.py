"""Recursos Humanos, step 3a / 3b: the year's holidays from the law (movable feasts, pontes), changed by the company;
the working days of a period (weekdays of the company, holidays skipped); the absence types."""
from datetime import date

import pytest

from app.services.employee_service import EmployeeError
from app.services.hr_calendar_service import (
    count_days, delete_absence_type, delete_holiday, easter, generate_holidays, list_absence_types, list_holidays,
    national_holidays, save_absence_type, save_holiday,
)
from app.services.payroll_settings_service import get_payroll_settings, update_payroll_settings


def test_the_law_holidays():
    assert easter(2026) == date(2026, 4, 5) and easter(2027) == date(2027, 3, 28)
    days = {d: (name, kind) for d, name, kind in national_holidays(2026)}
    assert days[date(2026, 2, 17)][0] == "Dia do Carnaval" and days[date(2026, 4, 3)][0] == "Sexta-Feira Santa"
    assert days[date(2026, 9, 18)] == ("Ponte (Dia do Fundador da Nação e do Herói Nacional)", "PONTE")  # 17/9 a Thursday
    assert date(2026, 2, 16) not in days  # Carnival (a Tuesday) gives no ponte
    assert date(2026, 1, 2) not in days  # nor New Year (a Thursday)
    assert len([d for d in days.values() if d[1] == "FERIADO"]) == 12


@pytest.mark.asyncio
async def test_the_calendar_and_the_working_days(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    year = await generate_holidays(db, company_id, 2026)
    assert year["added"] == 13 and (await generate_holidays(db, company_id, 2026))["added"] == 0  # only what is missing

    november = await count_days(db, company_id, date(2026, 11, 1), date(2026, 11, 30))
    assert november["days"] == 19 and [h["name"] for h in november["holidays"]] == ["Dia dos Finados", "Dia da Independência Nacional"]
    assert (await count_days(db, company_id, date(2026, 11, 1), date(2026, 11, 30), working_days=False))["days"] == 30

    # a bakery works on Saturdays; a tolerance decreed at the last minute; a ponte that does not apply
    settings = await get_payroll_settings(db, company_id)
    await update_payroll_settings(db, company_id, {**settings, "work_weekdays": [0, 1, 2, 3, 4, 5]})
    tolerance = await save_holiday(db, company_id, None, {"day": date(2026, 11, 27), "name": "Tolerância de ponto", "kind": "TOLERANCIA"})
    assert (await count_days(db, company_id, date(2026, 11, 1), date(2026, 11, 30)))["days"] == 22  # 25 - 2 holidays - 1 tolerance
    with pytest.raises(EmployeeError, match="já é feriado"):
        await save_holiday(db, company_id, None, {"day": date(2026, 11, 11), "name": "Outro"})
    ponte = next(h for h in (await list_holidays(db, company_id, 2026))["holidays"] if h["kind"] == "PONTE")
    await delete_holiday(db, company_id, ponte["id"])
    await delete_holiday(db, company_id, tolerance["id"])
    assert len((await list_holidays(db, company_id, 2026))["holidays"]) == 12
    with pytest.raises(EmployeeError, match="pelo menos um dia"):
        await update_payroll_settings(db, company_id, {**settings, "work_weekdays": []})
    with pytest.raises(EmployeeError, match="anterior"):
        await count_days(db, company_id, date(2026, 11, 30), date(2026, 11, 1))


@pytest.mark.asyncio
async def test_the_absence_types(db, company_with_essentials):
    company_id = company_with_essentials["company"].id
    types = (await list_absence_types(db, company_id))["types"]
    by_name = {t["name"]: t for t in types}
    assert by_name["Férias"]["takes_holiday_days"] and not by_name["Falta injustificada"]["paid"]
    assert not by_name["Licença de maternidade"]["working_days"]  # calendar days

    exam = await save_absence_type(db, company_id, None, {"name": "Doação de sangue", "category": "JUSTIFICADA", "paid": True,
                                                          "max_days": 1, "requires_document": True})
    assert exam["max_days"] == 1
    # only holidays take holiday days
    other = await save_absence_type(db, company_id, None, {"name": "Formação", "category": "JUSTIFICADA", "takes_holiday_days": True})
    assert not other["takes_holiday_days"]
    for data, message in (({"name": "férias", "category": "FERIAS"}, "Já existe"), ({"name": "X", "category": "?"}, "categoria"),
                          ({"name": "Y", "category": "LICENCA", "max_days": 0}, "entre 1 e 366"), ({"name": " ", "category": "LICENCA"}, "nome")):
        with pytest.raises(EmployeeError, match=message):
            await save_absence_type(db, company_id, None, data)
    await delete_absence_type(db, company_id, other["id"])
    assert len((await list_absence_types(db, company_id))["types"]) == len(types) + 1
