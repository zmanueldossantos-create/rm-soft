"""
Recursos Humanos, step 3a / 3b: the work calendar (working days of the week, holidays and pontes) and the absence
types - and the count of the working days of a period, which every absence uses.

The holidays of a year are generated from the law (Lei n.º 10/11, as changed by Lei n.º 11/18: 12 national holidays,
Carnival and Good Friday moving with Easter; a holiday on a Tuesday gives the Monday before as a «ponte», on a Thursday
the Friday after - not New Year, Carnival, All Souls' Day nor Christmas), then changed by the company: a ponte that
does not apply removed, a tolerance decreed by the Government added. Generating again only adds what is missing.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.hr_calendar import ABSENCE_CATEGORIES, HOLIDAY_KINDS, AbsenceType, HrHoliday
from app.services.employee_service import EmployeeError, EmployeeNotFoundError

WEEKDAYS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"]

# (month, day) or a movable feast, name, gives a ponte
NATIONAL_HOLIDAYS = (
    ((1, 1), "Dia do Ano Novo", False),
    ((2, 4), "Dia do Início da Luta Armada de Libertação Nacional", True),
    ("CARNAVAL", "Dia do Carnaval", False),
    ((3, 8), "Dia Internacional da Mulher", True),
    ((3, 23), "Dia da Libertação da África Austral", True),
    ((4, 4), "Dia da Paz e da Reconciliação Nacional", True),
    ("SEXTA_SANTA", "Sexta-Feira Santa", True),
    ((5, 1), "Dia Internacional do Trabalhador", True),
    ((9, 17), "Dia do Fundador da Nação e do Herói Nacional", True),
    ((11, 2), "Dia dos Finados", False),
    ((11, 11), "Dia da Independência Nacional", True),
    ((12, 25), "Dia de Natal e da Família", False),
)

# the starting absence types: name, category, paid, takes holiday days, working days, max days, document, notes
DEFAULT_ABSENCE_TYPES = (
    ("Férias", "FERIAS", True, True, True, None, False, None),
    ("Doença (com atestado médico)", "JUSTIFICADA", True, False, True, None, True, None),
    ("Casamento", "JUSTIFICADA", True, False, True, None, True, None),
    ("Falecimento de familiar", "JUSTIFICADA", True, False, True, None, True, None),
    ("Licença de maternidade", "LICENCA", True, False, False, None, True, "Dias de calendário"),
    ("Licença de paternidade", "JUSTIFICADA", True, False, True, None, True, None),
    ("Provas escolares", "JUSTIFICADA", True, False, True, None, True, None),
    ("Licença sem vencimento", "LICENCA", False, False, True, None, False, None),
    ("Falta injustificada", "INJUSTIFICADA", False, False, True, None, False, "Descontada no salário"),
)


def easter(year: int) -> date:
    """Easter Sunday (Gregorian calendar, anonymous algorithm)."""
    a, b, c = year % 19, year // 100, year % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = (h + l - 7 * m + 114) % 31 + 1
    return date(year, month, day)


def national_holidays(year: int) -> list[tuple[date, str, str]]:
    """The national holidays of a year and their pontes: (day, name, kind)."""
    out = []
    for when, name, bridge in NATIONAL_HOLIDAYS:
        if when == "CARNAVAL":
            day = easter(year) - timedelta(days=47)
        elif when == "SEXTA_SANTA":
            day = easter(year) - timedelta(days=2)
        else:
            day = date(year, *when)
        out.append((day, name, "FERIADO"))
        if bridge and day.weekday() == 1:
            out.append((day - timedelta(days=1), f"Ponte ({name})", "PONTE"))
        elif bridge and day.weekday() == 3:
            out.append((day + timedelta(days=1), f"Ponte ({name})", "PONTE"))
    return sorted(out)


# --- holidays ----------------------------------------------------------------------------------------------------

def _holiday(h: HrHoliday) -> dict:
    return {"id": h.id, "day": h.day, "name": h.name, "kind": h.kind, "kind_label": HOLIDAY_KINDS.get(h.kind),
            "weekday": WEEKDAYS[h.day.weekday()]}


async def list_holidays(db: AsyncSession, company_id: uuid.UUID, year: int) -> dict:
    rows = (await db.execute(select(HrHoliday).where(
        HrHoliday.company_id == company_id, HrHoliday.day >= date(year, 1, 1), HrHoliday.day <= date(year, 12, 31))
        .order_by(HrHoliday.day))).scalars().all()
    return {"year": year, "holidays": [_holiday(h) for h in rows],
            "kinds": [{"value": k, "label": v} for k, v in HOLIDAY_KINDS.items()]}


async def generate_holidays(db: AsyncSession, company_id: uuid.UUID, year: int) -> dict:
    """The year's national holidays and pontes - only the days not yet in the calendar."""
    if not 2000 <= year <= 2100:
        raise EmployeeError("Ano inválido")
    taken = set((await db.execute(select(HrHoliday.day).where(HrHoliday.company_id == company_id))).scalars())
    added = 0
    for day, name, kind in national_holidays(year):
        if day not in taken:
            db.add(HrHoliday(company_id=company_id, day=day, name=name, kind=kind))
            taken.add(day)
            added += 1
    await db.commit()
    return {**await list_holidays(db, company_id, year), "added": added}


def _clean_holiday(data: dict) -> tuple[date, str, str]:
    day = data.get("day")
    if isinstance(day, str) and day:
        day = date.fromisoformat(day)
    if not isinstance(day, date):
        raise EmployeeError("Indique o dia")
    name = " ".join((data.get("name") or "").split())[:120]
    if not name:
        raise EmployeeError("Indique o nome do feriado")
    kind = data.get("kind") or "FERIADO"
    if kind not in HOLIDAY_KINDS:
        raise EmployeeError("Tipo de feriado inválido")
    return day, name, kind


async def save_holiday(db: AsyncSession, company_id: uuid.UUID, holiday_id: uuid.UUID | None, data: dict) -> dict:
    day, name, kind = _clean_holiday(data)
    query = select(HrHoliday.name).where(HrHoliday.company_id == company_id, HrHoliday.day == day)
    if holiday_id is not None:
        query = query.where(HrHoliday.id != holiday_id)
    other = (await db.execute(query)).scalar_one_or_none()
    if other is not None:
        raise EmployeeError(f"{day:%d/%m/%Y} já é feriado: {other}")
    if holiday_id is None:
        holiday = HrHoliday(company_id=company_id, day=day, name=name, kind=kind)
        db.add(holiday)
    else:
        holiday = (await db.execute(select(HrHoliday).where(HrHoliday.id == holiday_id, HrHoliday.company_id == company_id))).scalar_one_or_none()
        if holiday is None:
            raise EmployeeNotFoundError("Feriado não encontrado")
        holiday.day, holiday.name, holiday.kind = day, name, kind
    await db.commit()
    await db.refresh(holiday)
    return _holiday(holiday)


async def delete_holiday(db: AsyncSession, company_id: uuid.UUID, holiday_id: uuid.UUID) -> None:
    holiday = (await db.execute(select(HrHoliday).where(HrHoliday.id == holiday_id, HrHoliday.company_id == company_id))).scalar_one_or_none()
    if holiday is None:
        raise EmployeeNotFoundError("Feriado não encontrado")
    await db.delete(holiday)
    await db.commit()


async def count_days(db: AsyncSession, company_id: uuid.UUID, start: date, end: date, working_days: bool = True) -> dict:
    """The days of a period: every day (calendar days), or only the working days - a working weekday that is no
    holiday, ponte or tolerance."""
    if end < start:
        raise EmployeeError("A data final é anterior à data inicial")
    total = (end - start).days + 1
    if not working_days:
        return {"days": total, "calendar_days": total, "holidays": []}
    from app.services.payroll_settings_service import ensure_payroll_defaults
    settings = await ensure_payroll_defaults(db, company_id)
    weekdays = set(settings.work_weekdays or [0, 1, 2, 3, 4])
    holidays = {h.day: h.name for h in (await db.execute(select(HrHoliday).where(
        HrHoliday.company_id == company_id, HrHoliday.day >= start, HrHoliday.day <= end))).scalars()}
    days, skipped = 0, []
    for k in range(total):
        day = start + timedelta(days=k)
        if day.weekday() not in weekdays:
            continue
        if day in holidays:
            skipped.append({"day": day, "name": holidays[day]})
            continue
        days += 1
    return {"days": days, "calendar_days": total, "holidays": skipped}


# --- absence types -----------------------------------------------------------------------------------------------

async def ensure_absence_types(db: AsyncSession, company_id: uuid.UUID) -> None:
    if (await db.execute(select(AbsenceType.id).where(AbsenceType.company_id == company_id))).first():
        return
    for position, (name, category, paid, holidays, working, max_days, document, notes) in enumerate(DEFAULT_ABSENCE_TYPES):
        db.add(AbsenceType(company_id=company_id, name=name, category=category, paid=paid, takes_holiday_days=holidays,
                           working_days=working, max_days=max_days, requires_document=document, notes=notes, position=position))
    await db.commit()


def _absence_type(t: AbsenceType) -> dict:
    return {"id": t.id, "name": t.name, "category": t.category, "category_label": ABSENCE_CATEGORIES.get(t.category),
            "paid": t.paid, "takes_holiday_days": t.takes_holiday_days, "working_days": t.working_days,
            "max_days": t.max_days, "requires_document": t.requires_document, "is_active": t.is_active,
            "position": t.position, "notes": t.notes}


async def list_absence_types(db: AsyncSession, company_id: uuid.UUID) -> dict:
    await ensure_absence_types(db, company_id)
    rows = (await db.execute(select(AbsenceType).where(AbsenceType.company_id == company_id)
                             .order_by(AbsenceType.position, AbsenceType.name))).scalars().all()
    return {"types": [_absence_type(t) for t in rows],
            "categories": [{"value": k, "label": v} for k, v in ABSENCE_CATEGORIES.items()]}


async def save_absence_type(db: AsyncSession, company_id: uuid.UUID, type_id: uuid.UUID | None, data: dict) -> dict:
    name = " ".join((data.get("name") or "").split())[:120]
    if not name:
        raise EmployeeError("Indique o nome do tipo de ausência")
    category = data.get("category")
    if category not in ABSENCE_CATEGORIES:
        raise EmployeeError("Escolha a categoria")
    max_days = data.get("max_days")
    if max_days in (None, ""):
        max_days = None
    else:
        try:
            max_days = int(max_days)
        except (TypeError, ValueError):
            raise EmployeeError("Máximo de dias: indique um número inteiro")
        if not 1 <= max_days <= 366:
            raise EmployeeError("Máximo de dias: entre 1 e 366")
    query = select(AbsenceType.id).where(AbsenceType.company_id == company_id, func.lower(AbsenceType.name) == name.lower())
    if type_id is not None:
        query = query.where(AbsenceType.id != type_id)
    if (await db.execute(query)).first():
        raise EmployeeError(f"Já existe o tipo de ausência «{name}»")
    values = {"name": name, "category": category, "paid": bool(data.get("paid")),
              "takes_holiday_days": bool(data.get("takes_holiday_days")) and category == "FERIAS",
              "working_days": bool(data.get("working_days", True)), "max_days": max_days,
              "requires_document": bool(data.get("requires_document")), "is_active": bool(data.get("is_active", True)),
              "notes": " ".join((data.get("notes") or "").split())[:300] or None}
    if type_id is None:
        await ensure_absence_types(db, company_id)
        position = (await db.execute(select(func.coalesce(func.max(AbsenceType.position), -1)).where(
            AbsenceType.company_id == company_id))).scalar_one() + 1
        absence_type = AbsenceType(company_id=company_id, position=position, **values)
        db.add(absence_type)
    else:
        absence_type = (await db.execute(select(AbsenceType).where(
            AbsenceType.id == type_id, AbsenceType.company_id == company_id))).scalar_one_or_none()
        if absence_type is None:
            raise EmployeeNotFoundError("Tipo de ausência não encontrado")
        for field, value in values.items():
            setattr(absence_type, field, value)
    await db.commit()
    await db.refresh(absence_type)
    return _absence_type(absence_type)


async def delete_absence_type(db: AsyncSession, company_id: uuid.UUID, type_id: uuid.UUID) -> None:
    """A type no absence uses: a used one is switched off instead (its absences keep it)."""
    from app.models.absence import Absence
    absence_type = (await db.execute(select(AbsenceType).where(
        AbsenceType.id == type_id, AbsenceType.company_id == company_id))).scalar_one_or_none()
    if absence_type is None:
        raise EmployeeNotFoundError("Tipo de ausência não encontrado")
    used = (await db.execute(select(func.count()).select_from(Absence).where(Absence.type_id == absence_type.id))).scalar_one()
    if used:
        raise EmployeeError(f"«{absence_type.name}» tem {used} ausência(s): desative-o em vez de o apagar")
    await db.delete(absence_type)
    await db.commit()
