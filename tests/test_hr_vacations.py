"""Recursos Humanos, step 3d: the holiday balance - the year's days, the year of the admission per complete month, what
passes to the next year (all of it or up to a limit), the corrections, the approved and asked holidays, and a request
beyond the balance refused unless the company allows it."""
from datetime import date
from types import SimpleNamespace

import pytest

from app.services.absence_service import approve_absence, create_absence
from app.services.employee_service import EmployeeError, create_employee, get_employee
from app.services.hr_calendar_service import generate_holidays, list_absence_types
from app.services.payroll_settings_service import update_payroll_settings
from app.services.vacation_service import (
    add_adjustment, delete_adjustment, entitled_days, list_adjustments, vacation_overview,
)


def test_the_days_of_a_year():
    rules = SimpleNamespace(vacation_days_year=22, vacation_days_per_month_first_year=2)
    old = SimpleNamespace(hired_on=date(2024, 3, 1), left_on=None)
    assert entitled_days(old, 2026, rules) == 22
    assert entitled_days(old, 2024, rules, today=date(2026, 1, 1)) == 20  # March to December: 10 complete months
    assert entitled_days(old, 2023, rules) == 0
    new = SimpleNamespace(hired_on=date(2026, 9, 15), left_on=None)
    assert entitled_days(new, 2026, rules, today=date(2026, 11, 18)) == 4  # 15/9-14/10 and 15/10-14/11
    assert entitled_days(new, 2026, rules, today=date(2026, 9, 30)) == 0


@pytest.mark.asyncio
async def test_the_balance_and_the_limit(db, company_with_essentials):
    ctx = company_with_essentials
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    await generate_holidays(db, company_id, 2026)
    maria = await create_employee(db, company_id, user_id, {"full_name": "Maria Lopes", "hired_on": date(2024, 3, 1),
                                                            "base_salary": 180000, "payment_method": "NUMERARIO"})
    holidays = next(t for t in (await list_absence_types(db, company_id))["types"] if t["name"] == "Férias")
    await update_payroll_settings(db, company_id, {"vacation_start_year": 2024})  # balances followed from 2024

    # the years before RM SOFT: taken on paper
    await add_adjustment(db, company_id, user_id, maria["id"], 2024, -20, "Gozadas antes do RM SOFT")
    await add_adjustment(db, company_id, user_id, maria["id"], 2025, -22, "Gozadas antes do RM SOFT")
    with pytest.raises(EmployeeError, match="motivo"):
        await add_adjustment(db, company_id, user_id, maria["id"], 2025, 2, " ")
    row = next(r for r in (await vacation_overview(db, company_id, 2026))["employees"] if r["name"] == "Maria Lopes")
    assert (row["entitled"], row["brought"], row["balance"]) == (22, 0, 22)

    # 3 to 20 November: 13 working days (the 11th is a holiday) - approved
    first = await create_absence(db, company_id, user_id, {"employee_id": maria["id"], "type_id": holidays["id"],
                                                           "start_date": date(2026, 11, 3), "end_date": date(2026, 11, 20)}, approve=True)
    assert first["days"] == 13
    asked = await create_absence(db, company_id, user_id, {"employee_id": maria["id"], "type_id": holidays["id"],
                                                           "start_date": date(2026, 12, 1), "end_date": date(2026, 12, 4)})
    row = next(r for r in (await vacation_overview(db, company_id, 2026))["employees"] if r["name"] == "Maria Lopes")
    assert (row["taken"], row["asked"], row["balance"], row["available"]) == (13, 4, 9, 5)
    with pytest.raises(EmployeeError, match="Saldo de férias insuficiente em 2026: 5 dia"):
        await create_absence(db, company_id, user_id, {"employee_id": maria["id"], "type_id": holidays["id"],
                                                       "start_date": date(2026, 12, 14), "end_date": date(2026, 12, 21)})
    await approve_absence(db, company_id, user_id, asked["id"])

    # the company allows going beyond
    await update_payroll_settings(db, company_id, {"vacation_allow_negative": True})
    beyond = await create_absence(db, company_id, user_id, {"employee_id": maria["id"], "type_id": holidays["id"],
                                                            "start_date": date(2026, 12, 14), "end_date": date(2026, 12, 21)})
    assert beyond["days"] == 6

    # what passes to 2027: 5 left, at most 3 when the company limits it
    row = next(r for r in (await vacation_overview(db, company_id, 2027))["employees"] if r["name"] == "Maria Lopes")
    assert (row["brought"], row["entitled"], row["balance"]) == (5, 22, 27)
    await update_payroll_settings(db, company_id, {"vacation_carry_max": 3})
    row = next(r for r in (await vacation_overview(db, company_id, 2027))["employees"] if r["name"] == "Maria Lopes")
    assert (row["brought"], row["balance"]) == (3, 25)

    adjustments = await list_adjustments(db, company_id, maria["id"], 2025)
    assert adjustments[0]["days"] == -22 and adjustments[0]["created_by"]
    await delete_adjustment(db, company_id, adjustments[0]["id"])
    row = next(r for r in (await vacation_overview(db, company_id, 2026))["employees"] if r["name"] == "Maria Lopes")
    assert row["brought"] == 3  # 2025's 22 days are back, but only 3 pass to the next year

    # a company starting with RM SOFT in 2026: the years before are not followed (their balance is a correction)
    await update_payroll_settings(db, company_id, {"vacation_start_year": 2026})
    row = next(r for r in (await vacation_overview(db, company_id, 2026))["employees"] if r["name"] == "Maria Lopes")
    assert (row["brought"], row["entitled"]) == (0, 22)
    assert (await get_employee(db, company_id, maria["id"])).full_name == "Maria Lopes"
