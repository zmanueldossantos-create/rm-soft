"""
Recursos Humanos, step 3d: the holiday balance (férias) of each employee, year by year - all of it from the company's
settings (Parâmetros de RH), none of it coded:

    entitled  the year's days (22 by default); in the year of the admission, days per complete month worked
              (2 by default) up to the year's days;
    brought   what was left the year before (all of it, or up to the company's limit); a debt (taken beyond) is
              brought whole; nothing before the year the company started counting (vacation_start_year: what was left
              then is typed as a correction of that year);
    adjusted  the corrections typed by the RH (the balance brought from before RM SOFT, days agreed);
    taken     the approved absences whose type «takes holiday days», counted in that year;
    asked     the ones still waiting for a decision;
    balance = entitled + brought + adjusted - taken.

A holiday request beyond the balance (the asked ones included) is refused unless the company allows it.
"""
import uuid
from datetime import date, timedelta

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.absence import Absence, AbsenceStatus, VacationAdjustment
from app.models.employee import Employee
from app.models.hr_calendar import AbsenceType
from app.models.user import User
from app.services.employee_service import EmployeeError, EmployeeNotFoundError, get_employee
from app.services.hr_calendar_service import count_days

HISTORY_YEARS = 10  # how far back a balance is followed


def _add_months(day: date, months: int) -> date:
    year, month = divmod(day.month - 1 + months, 12)
    year += day.year
    month += 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def _months_completed(start: date, end: date) -> int:
    """Complete months from start to end, end included (1 March -> 31 March = 1; 15 March -> 13 April = 0)."""
    months = 0
    while _add_months(start, months + 1) - timedelta(days=1) <= end:
        months += 1
    return months


def entitled_days(employee: Employee, year: int, settings, today: date | None = None) -> float:
    today = today or date.today()
    if employee.hired_on.year > year or (employee.left_on is not None and employee.left_on.year < year):
        return 0.0
    annual = float(settings.vacation_days_year)
    if employee.hired_on.year < year:
        return annual
    # the year of the admission: per complete month worked, up to today (or the end of the year, or his last day)
    end = min(date(year, 12, 31), today, employee.left_on or date(year, 12, 31))
    return min(annual, _months_completed(employee.hired_on, end) * float(settings.vacation_days_per_month_first_year))


async def _days_in_year(db: AsyncSession, company_id: uuid.UUID, absence: Absence, absence_type: AbsenceType, year: int) -> float:
    start, end = max(absence.start_date, date(year, 1, 1)), min(absence.end_date, date(year, 12, 31))
    if end < start:
        return 0.0
    if start == absence.start_date and end == absence.end_date:
        return float(absence.days)
    return float((await count_days(db, company_id, start, end, absence_type.working_days))["days"])


async def _used(db: AsyncSession, company_id: uuid.UUID, employee_ids: list[uuid.UUID], years: range) -> dict:
    """{(employee, year): {"taken": days approved, "asked": days asked}} for the absences that take holiday days."""
    types = {t.id: t for t in (await db.execute(select(AbsenceType).where(
        AbsenceType.company_id == company_id, AbsenceType.takes_holiday_days.is_(True)))).scalars()}
    out: dict = {}
    if not types or not employee_ids:
        return out
    rows = (await db.execute(select(Absence).where(
        Absence.employee_id.in_(employee_ids), Absence.type_id.in_(list(types)),
        Absence.status.in_((AbsenceStatus.APROVADA, AbsenceStatus.PEDIDA)),
        Absence.end_date >= date(years.start, 1, 1), Absence.start_date <= date(years.stop - 1, 12, 31)))).scalars().all()
    for a in rows:
        for year in range(max(a.start_date.year, years.start), min(a.end_date.year, years.stop - 1) + 1):
            days = await _days_in_year(db, company_id, a, types[a.type_id], year)
            slot = out.setdefault((a.employee_id, year), {"taken": 0.0, "asked": 0.0})
            slot["taken" if a.status == AbsenceStatus.APROVADA else "asked"] += days
    return out


async def balances(db: AsyncSession, company_id: uuid.UUID, employees: list[Employee], year: int,
                   today: date | None = None) -> dict:
    """The balance of each employee for the year, followed from his admission (at most HISTORY_YEARS back)."""
    from app.services.payroll_settings_service import ensure_payroll_defaults
    settings = await ensure_payroll_defaults(db, company_id)
    start_year = settings.vacation_start_year or (year - HISTORY_YEARS)
    begin = lambda e: max(e.hired_on.year, year - HISTORY_YEARS, start_year)  # noqa: E731
    first = min([begin(e) for e in employees] or [year])
    years = range(first, year + 1)
    ids = [e.id for e in employees]
    used = await _used(db, company_id, ids, years)
    adjusted: dict = {}
    for adj in (await db.execute(select(VacationAdjustment).where(
            VacationAdjustment.employee_id.in_(ids or [uuid.uuid4()]), VacationAdjustment.year >= first,
            VacationAdjustment.year <= year))).scalars():
        adjusted[(adj.employee_id, adj.year)] = adjusted.get((adj.employee_id, adj.year), 0.0) + float(adj.days)
    cap = None if settings.vacation_carry_max is None else float(settings.vacation_carry_max)
    out = {}
    for e in employees:
        left = 0.0
        for y in range(begin(e), year + 1):
            brought = left if left < 0 else (left if cap is None else min(left, cap))
            entitled = entitled_days(e, y, settings, today)
            slot = used.get((e.id, y), {"taken": 0.0, "asked": 0.0})
            adj = adjusted.get((e.id, y), 0.0)
            left = entitled + brought + adj - slot["taken"]
            if y == year:
                out[e.id] = {"entitled": round(entitled, 1), "brought": round(brought, 1), "adjusted": round(adj, 1),
                             "taken": round(slot["taken"], 1), "asked": round(slot["asked"], 1), "balance": round(left, 1),
                             "available": round(left - slot["asked"], 1)}
        if e.id not in out:  # admitted after that year
            out[e.id] = {"entitled": 0.0, "brought": 0.0, "adjusted": 0.0, "taken": 0.0, "asked": 0.0, "balance": 0.0, "available": 0.0}
    return out


async def vacation_overview(db: AsyncSession, company_id: uuid.UUID, year: int) -> dict:
    """Every employee working for the company in that year, with his balance."""
    if not 2000 <= year <= 2100:
        raise EmployeeError("Ano inválido")
    employees = (await db.execute(select(Employee).where(
        Employee.company_id == company_id, Employee.hired_on <= date(year, 12, 31),
        or_(Employee.left_on.is_(None), Employee.left_on >= date(year, 1, 1))).order_by(Employee.full_name))).scalars().all()
    data = await balances(db, company_id, list(employees), year)
    return {"year": year, "employees": [{"employee_id": e.id, "name": e.full_name, "number": e.number, "hired_on": e.hired_on,
                                         "is_active": e.is_active, **data[e.id]} for e in employees]}


async def check_vacation_balance(db: AsyncSession, company_id: uuid.UUID, employee: Employee, absence_type: AbsenceType,
                                 start: date, days: float, exclude_id: uuid.UUID | None = None, approving: bool = False) -> None:
    """A holiday absence that would go beyond the balance is refused, unless the company allows it. Asking counts
    the other requests still waiting; approving counts only what is approved."""
    if not absence_type.takes_holiday_days:
        return
    from app.services.payroll_settings_service import ensure_payroll_defaults
    settings = await ensure_payroll_defaults(db, company_id)
    if settings.vacation_allow_negative:
        return
    year = start.year
    data = (await balances(db, company_id, [employee], year))[employee.id]
    asked = data["asked"]
    if exclude_id is not None:  # the absence itself, when it is asked already
        current = await db.get(Absence, exclude_id)
        if current is not None and current.status == AbsenceStatus.PEDIDA and current.start_date.year == year:
            asked -= float(current.days)
    free = data["balance"] - (0 if approving else asked)
    if days > free + 1e-9:
        raise EmployeeError(f"Saldo de férias insuficiente em {year}: {free:g} dia(s) disponível(eis), pedidos {days:g}")


async def list_adjustments(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, year: int) -> list[dict]:
    await get_employee(db, company_id, employee_id)
    users = dict((await db.execute(select(User.id, User.full_name).where(User.company_id == company_id))).all())
    rows = (await db.execute(select(VacationAdjustment).where(
        VacationAdjustment.employee_id == employee_id, VacationAdjustment.year == year)
        .order_by(VacationAdjustment.created_at))).scalars().all()
    return [{"id": a.id, "year": a.year, "days": float(a.days), "note": a.note, "created_by": users.get(a.created_by_user_id),
             "created_at": a.created_at} for a in rows]


async def add_adjustment(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, employee_id: uuid.UUID,
                         year: int, days, note: str | None) -> list[dict]:
    employee = await get_employee(db, company_id, employee_id)
    try:
        days = round(float(days), 1)
    except (TypeError, ValueError):
        raise EmployeeError("Indique os dias (ex.: 5 ou -2)")
    if days == 0 or abs(days) > 366:
        raise EmployeeError("Indique os dias (ex.: 5 ou -2)")
    if not employee.hired_on.year <= year <= date.today().year + 1:
        raise EmployeeError(f"Ano inválido para {employee.full_name}")
    note = " ".join((note or "").split())[:300]
    if not note:
        raise EmployeeError("Indique o motivo do ajuste")
    db.add(VacationAdjustment(company_id=company_id, employee_id=employee.id, year=year, days=days, note=note,
                              created_by_user_id=user_id))
    await db.commit()
    return await list_adjustments(db, company_id, employee_id, year)


async def delete_adjustment(db: AsyncSession, company_id: uuid.UUID, adjustment_id: uuid.UUID) -> None:
    adj = (await db.execute(select(VacationAdjustment).where(
        VacationAdjustment.id == adjustment_id, VacationAdjustment.company_id == company_id))).scalar_one_or_none()
    if adj is None:
        raise EmployeeNotFoundError("Ajuste não encontrado")
    await db.delete(adj)
    await db.commit()
