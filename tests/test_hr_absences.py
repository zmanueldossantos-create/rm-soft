"""Recursos Humanos, step 3c: an absence asked, approved, refused, cancelled; its days counted by its type (working
days without holidays, calendar days, half a day); overlaps, limits, the employee's dates and the justifying document
refused or required; the month's map of the team."""
from datetime import date

import pytest

from app.services.absence_service import (
    approve_absence, attach_document, cancel_absence, create_absence, list_absences, month_map, refuse_absence, update_absence,
)
from app.services.employee_service import EmployeeError, create_employee, register_departure
from app.services.hr_calendar_service import (
    delete_absence_type, generate_holidays, list_absence_types, save_absence_type,
)

IBAN = "AO06004000000123456789027"
PDF = b"%PDF-1.4\n%fake\n"


async def _setup(db, ctx):
    company_id, user_id = ctx["company"].id, ctx["gestor"].id
    await generate_holidays(db, company_id, 2026)
    maria = await create_employee(db, company_id, user_id, {"full_name": "Maria Lopes", "hired_on": date(2024, 3, 1),
                                                            "base_salary": 180000, "payment_method": "NUMERARIO"})
    types = {t["name"]: t for t in (await list_absence_types(db, company_id))["types"]}
    return company_id, user_id, maria, types


def _absence(employee, absence_type, start, end=None, **extra):
    return {"employee_id": employee["id"], "type_id": absence_type["id"], "start_date": start, "end_date": end or start, **extra}


@pytest.mark.asyncio
async def test_holidays_asked_approved_and_counted(db, company_with_essentials):
    company_id, user_id, maria, types = await _setup(db, company_with_essentials)
    # 9 to 20 November 2026: 10 weekdays, the 11th (Independence) is a holiday -> 9 working days
    asked = await create_absence(db, company_id, user_id, _absence(maria, types["Férias"], date(2026, 11, 9), date(2026, 11, 20)))
    assert asked["status"] == "PEDIDA" and asked["days"] == 9
    assert (await list_absences(db, company_id))["pending"] == 1
    changed = await update_absence(db, company_id, asked["id"], _absence(maria, types["Férias"], date(2026, 11, 9), date(2026, 11, 13)))
    assert changed["days"] == 4
    approved = await approve_absence(db, company_id, user_id, asked["id"], "Bom descanso")
    assert approved["status"] == "APROVADA" and approved["decided_by"] and approved["decision_note"] == "Bom descanso"
    with pytest.raises(EmployeeError, match="já não se altera"):
        await update_absence(db, company_id, asked["id"], _absence(maria, types["Férias"], date(2026, 11, 9)))
    # overlapping another one
    with pytest.raises(EmployeeError, match="já tem uma ausência de 09/11/2026"):
        await create_absence(db, company_id, user_id, _absence(maria, types["Falta injustificada"], date(2026, 11, 12)))
    cancelled = await cancel_absence(db, company_id, user_id, asked["id"], "Adiado")
    assert cancelled["status"] == "CANCELADA"
    again = await create_absence(db, company_id, user_id, _absence(maria, types["Falta injustificada"], date(2026, 11, 12),
                                                                   half_day=True), approve=True)
    assert again["status"] == "APROVADA" and again["days"] == 0.5  # approved at once, half a day


@pytest.mark.asyncio
async def test_what_an_absence_refuses(db, company_with_essentials):
    company_id, user_id, maria, types = await _setup(db, company_with_essentials)
    unjustified = types["Falta injustificada"]
    for data, message in (
        (_absence(maria, unjustified, date(2026, 11, 14)), "Nenhum dia útil"),  # a Saturday
        (_absence(maria, unjustified, date(2026, 11, 11)), "Nenhum dia útil"),  # a holiday
        (_absence(maria, unjustified, date(2026, 11, 10), date(2026, 11, 9)), "anterior ao primeiro"),
        (_absence(maria, unjustified, date(2026, 11, 9), date(2026, 11, 10), half_day=True), "Meio dia"),
        (_absence(maria, unjustified, date(2024, 2, 1)), "foi admitido em 01/03/2024"),
        ({**_absence(maria, unjustified, date(2026, 11, 9)), "type_id": None}, "tipo de ausência"),
    ):
        with pytest.raises(EmployeeError, match=message):
            await create_absence(db, company_id, user_id, data)
    blood = await save_absence_type(db, company_id, None, {"name": "Doação de sangue", "category": "JUSTIFICADA", "paid": True, "max_days": 1})
    with pytest.raises(EmployeeError, match="no máximo 1 dia"):
        await create_absence(db, company_id, user_id, _absence(maria, blood, date(2026, 11, 9), date(2026, 11, 10)))
    # maternity counts calendar days, the weekend and the holiday included
    maternity = await create_absence(db, company_id, user_id, _absence(maria, types["Licença de maternidade"], date(2026, 11, 9), date(2026, 11, 15)))
    assert maternity["days"] == 7
    # a gone employee
    joao = await create_employee(db, company_id, user_id, {"full_name": "João", "hired_on": date(2024, 1, 1), "base_salary": 100000,
                                                           "payment_method": "NUMERARIO"})
    await register_departure(db, company_id, joao["id"], date(2026, 10, 31), "DEMISSAO")
    with pytest.raises(EmployeeError, match="saiu da empresa"):
        await create_absence(db, company_id, user_id, _absence(joao, unjustified, date(2026, 11, 9)))
    # a type in use is switched off, not deleted
    with pytest.raises(EmployeeError, match="desative-o"):
        await delete_absence_type(db, company_id, types["Licença de maternidade"]["id"])


@pytest.mark.asyncio
async def test_the_justifying_document_and_a_refusal(db, company_with_essentials):
    company_id, user_id, maria, types = await _setup(db, company_with_essentials)
    sick = types["Doença (com atestado médico)"]
    with pytest.raises(EmployeeError, match="registe-a como pedida"):
        await create_absence(db, company_id, user_id, _absence(maria, sick, date(2026, 11, 9)), approve=True)
    asked = await create_absence(db, company_id, user_id, _absence(maria, sick, date(2026, 11, 9), date(2026, 11, 10)))
    with pytest.raises(EmployeeError, match="precisa do documento"):
        await approve_absence(db, company_id, user_id, asked["id"])
    with_document = await attach_document(db, company_id, user_id, asked["id"], "atestado.pdf", PDF)
    assert with_document["document_id"] is not None
    assert (await approve_absence(db, company_id, user_id, asked["id"]))["status"] == "APROVADA"

    other = await create_absence(db, company_id, user_id, _absence(maria, types["Férias"], date(2026, 12, 21), date(2026, 12, 24)))
    with pytest.raises(EmployeeError, match="motivo da recusa"):
        await refuse_absence(db, company_id, user_id, other["id"], " ")
    refused = await refuse_absence(db, company_id, user_id, other["id"], "Época alta")
    assert refused["status"] == "RECUSADA"
    with pytest.raises(EmployeeError, match="recusada"):
        await approve_absence(db, company_id, user_id, other["id"])


@pytest.mark.asyncio
async def test_the_month_map(db, company_with_essentials):
    company_id, user_id, maria, types = await _setup(db, company_with_essentials)
    await create_absence(db, company_id, user_id, _absence(maria, types["Férias"], date(2026, 11, 9), date(2026, 11, 13)), approve=True)
    await create_absence(db, company_id, user_id, _absence(maria, types["Falta injustificada"], date(2026, 11, 16)))  # asked only
    november = await month_map(db, company_id, 2026, 11)
    assert len(november["days"]) == 30
    assert next(d for d in november["days"] if d["day"] == date(2026, 11, 11))["holiday"] == "Dia da Independência Nacional"
    row = next(r for r in november["employees"] if r["name"] == "Maria Lopes")
    assert sorted(row["cells"]) == ["2026-11-09", "2026-11-10", "2026-11-12", "2026-11-13", "2026-11-16"]  # not the holiday
    assert row["cells"]["2026-11-16"]["pending"] and row["absent_days"] == 4
