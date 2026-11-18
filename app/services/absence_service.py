"""
Recursos Humanos, step 3c: the employees' absences - registered (asked, or approved at once by who may approve),
approved or refused, cancelled - and the month's map of the team.

Rules:
- the employee works for the company on those days (admitted before, not gone yet);
- the days are counted by the absence's type: working days (the company's weekdays, without holidays and pontes) or
  calendar days; half a day only for a single day; a period with no day to count is refused (a Saturday off);
- the type's limit of days, and two absences of an employee never overlap (refused and cancelled ones aside);
- a type that requires a document is approved only with it (it can be asked without, the document comes later);
- changed only while asked; cancelled while asked or approved; the decision (who, when, a note) is kept.
"""
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.absence import Absence, AbsenceStatus
from app.models.employee import Employee
from app.models.hr_calendar import ABSENCE_CATEGORIES, AbsenceType, HrHoliday
from app.models.user import User
from app.services.employee_service import EmployeeError, EmployeeNotFoundError, get_employee
from app.services.hr_calendar_service import count_days, ensure_absence_types

STATUS_LABELS = {AbsenceStatus.PEDIDA: "Pedida", AbsenceStatus.APROVADA: "Aprovada", AbsenceStatus.RECUSADA: "Recusada",
                 AbsenceStatus.CANCELADA: "Cancelada"}
LIVE = (AbsenceStatus.PEDIDA, AbsenceStatus.APROVADA)


def _day(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise EmployeeError(f"{label}: data inválida")


async def _get(db: AsyncSession, company_id: uuid.UUID, absence_id: uuid.UUID) -> Absence:
    absence = (await db.execute(select(Absence).where(Absence.id == absence_id, Absence.company_id == company_id))).scalar_one_or_none()
    if absence is None:
        raise EmployeeNotFoundError("Ausência não encontrada")
    return absence


async def _check(db: AsyncSession, company_id: uuid.UUID, data: dict, current: Absence | None) -> dict:
    try:
        employee_id = uuid.UUID(str(data.get("employee_id")))
    except ValueError:
        raise EmployeeError("Escolha o colaborador")
    employee = await get_employee(db, company_id, employee_id)
    try:
        type_id = uuid.UUID(str(data.get("type_id")))
    except ValueError:
        raise EmployeeError("Escolha o tipo de ausência")
    absence_type = (await db.execute(select(AbsenceType).where(
        AbsenceType.id == type_id, AbsenceType.company_id == company_id))).scalar_one_or_none()
    if absence_type is None:
        raise EmployeeError("Escolha o tipo de ausência")
    if not absence_type.is_active and (current is None or current.type_id != type_id):
        raise EmployeeError(f"«{absence_type.name}» está desativado")
    start = _day(data.get("start_date"), "Início")
    end = _day(data.get("end_date"), "Fim") or start
    if start is None:
        raise EmployeeError("Indique o primeiro dia da ausência")
    if end < start:
        raise EmployeeError("O último dia é anterior ao primeiro")
    if (end - start).days > 366:
        raise EmployeeError("Uma ausência dura no máximo um ano")
    half = bool(data.get("half_day"))
    if half and end != start:
        raise EmployeeError("Meio dia só se aplica a uma ausência de um dia")
    if start < employee.hired_on:
        raise EmployeeError(f"{employee.full_name} foi admitido em {employee.hired_on:%d/%m/%Y}")
    if employee.left_on is not None and end > employee.left_on:
        raise EmployeeError(f"{employee.full_name} saiu da empresa em {employee.left_on:%d/%m/%Y}")
    counted = await count_days(db, company_id, start, end, absence_type.working_days)
    days = counted["days"] * (0.5 if half else 1)
    if days <= 0:
        raise EmployeeError("Nenhum dia útil neste período (fim de semana ou feriado)")
    if absence_type.max_days and days > absence_type.max_days:
        raise EmployeeError(f"«{absence_type.name}»: no máximo {absence_type.max_days} dia(s) por ausência")
    overlap = select(Absence).where(Absence.employee_id == employee.id, Absence.status.in_(LIVE),
                                    Absence.start_date <= end, Absence.end_date >= start)
    if current is not None:
        overlap = overlap.where(Absence.id != current.id)
    other = (await db.execute(overlap)).scalars().first()
    if other is not None:
        raise EmployeeError(f"{employee.full_name} já tem uma ausência de {other.start_date:%d/%m/%Y} a {other.end_date:%d/%m/%Y}")
    reason = " ".join((data.get("reason") or "").split())[:500] or None
    return {"employee_id": employee.id, "type_id": absence_type.id, "start_date": start, "end_date": end, "half_day": half,
            "days": days, "reason": reason, "_type": absence_type, "_employee": employee}


def _decide(absence: Absence, status: AbsenceStatus, user_id: uuid.UUID | None, note: str | None) -> None:
    absence.status, absence.decided_by_user_id, absence.decided_at = status, user_id, datetime.now(timezone.utc)
    absence.decision_note = " ".join((note or "").split())[:300] or None


async def _require_document(db: AsyncSession, absence: Absence, absence_type: AbsenceType) -> None:
    if absence_type.requires_document and absence.document_id is None:
        raise EmployeeError(f"«{absence_type.name}» precisa do documento justificativo para ser aprovada")


async def create_absence(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, data: dict,
                         approve: bool = False) -> dict:
    """Asked - or approved at once (approve: the caller may approve)."""
    clean = await _check(db, company_id, data, None)
    absence_type = clean.pop("_type")
    clean.pop("_employee")
    if approve and absence_type.requires_document:
        raise EmployeeError(f"«{absence_type.name}» precisa do documento justificativo: registe-a como pedida e junte-o")
    absence = Absence(company_id=company_id, requested_by_user_id=user_id, status=AbsenceStatus.PEDIDA, **clean)
    db.add(absence)
    if approve:
        _decide(absence, AbsenceStatus.APROVADA, user_id, None)
    await db.commit()
    return await absence_detail(db, company_id, absence.id)


async def update_absence(db: AsyncSession, company_id: uuid.UUID, absence_id: uuid.UUID, data: dict) -> dict:
    absence = await _get(db, company_id, absence_id)
    if absence.status != AbsenceStatus.PEDIDA:
        raise EmployeeError(f"Uma ausência {STATUS_LABELS[absence.status].lower()} já não se altera")
    clean = await _check(db, company_id, {**data, "employee_id": absence.employee_id}, absence)
    clean.pop("_type")
    clean.pop("_employee")
    for field, value in clean.items():
        setattr(absence, field, value)
    await db.commit()
    return await absence_detail(db, company_id, absence_id)


async def approve_absence(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, absence_id: uuid.UUID,
                          note: str | None = None) -> dict:
    absence = await _get(db, company_id, absence_id)
    if absence.status != AbsenceStatus.PEDIDA:
        raise EmployeeError(f"Esta ausência está {STATUS_LABELS[absence.status].lower()}")
    absence_type = await db.get(AbsenceType, absence.type_id)
    await _require_document(db, absence, absence_type)
    # checked again: the calendar or another absence may have changed since it was asked
    await _check(db, company_id, {"employee_id": absence.employee_id, "type_id": absence.type_id, "start_date": absence.start_date,
                                  "end_date": absence.end_date, "half_day": absence.half_day, "reason": absence.reason}, absence)
    _decide(absence, AbsenceStatus.APROVADA, user_id, note)
    await db.commit()
    return await absence_detail(db, company_id, absence_id)


async def refuse_absence(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, absence_id: uuid.UUID,
                         note: str | None) -> dict:
    absence = await _get(db, company_id, absence_id)
    if absence.status != AbsenceStatus.PEDIDA:
        raise EmployeeError(f"Esta ausência está {STATUS_LABELS[absence.status].lower()}")
    if not (note or "").strip():
        raise EmployeeError("Indique o motivo da recusa")
    _decide(absence, AbsenceStatus.RECUSADA, user_id, note)
    await db.commit()
    return await absence_detail(db, company_id, absence_id)


async def cancel_absence(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, absence_id: uuid.UUID,
                         note: str | None) -> dict:
    absence = await _get(db, company_id, absence_id)
    if absence.status not in LIVE:
        raise EmployeeError(f"Esta ausência está {STATUS_LABELS[absence.status].lower()}")
    _decide(absence, AbsenceStatus.CANCELADA, user_id, note)
    await db.commit()
    return await absence_detail(db, company_id, absence_id)


async def attach_document(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, absence_id: uuid.UUID,
                          file_name: str | None, content: bytes) -> dict:
    """The justifying document: kept with the employee's documents, linked to the absence."""
    from app.services.employee_file_service import add_document
    absence = await _get(db, company_id, absence_id)
    if absence.status not in LIVE:
        raise EmployeeError(f"Esta ausência está {STATUS_LABELS[absence.status].lower()}")
    absence_type = await db.get(AbsenceType, absence.type_id)
    if not content:
        raise EmployeeError("Escolha o ficheiro")
    period = f"{absence.start_date:%d/%m/%Y}" + (f" a {absence.end_date:%d/%m/%Y}" if absence.end_date != absence.start_date else "")
    absence_pk = absence.id
    document = await add_document(db, company_id, user_id, absence.employee_id, None, f"Justificativo: {absence_type.name} ({period})",
                                  date.today(), None, file_name, content)
    absence = await _get(db, company_id, absence_pk)
    absence.document_id = document["id"]
    await db.commit()
    return await absence_detail(db, company_id, absence_pk)


def _absence(a: Absence, types: dict, employees: dict, users: dict) -> dict:
    t = types.get(a.type_id)
    e = employees.get(a.employee_id)
    return {
        "id": a.id, "employee_id": a.employee_id, "employee_name": e.full_name if e else None, "employee_number": e.number if e else None,
        "type_id": a.type_id, "type_name": t.name if t else None, "category": t.category if t else None,
        "category_label": ABSENCE_CATEGORIES.get(t.category) if t else None, "paid": t.paid if t else None,
        "requires_document": t.requires_document if t else False, "start_date": a.start_date, "end_date": a.end_date,
        "half_day": a.half_day, "days": float(a.days), "reason": a.reason, "document_id": a.document_id,
        "status": a.status.value, "status_label": STATUS_LABELS[a.status], "decision_note": a.decision_note,
        "requested_by": users.get(a.requested_by_user_id), "decided_by": users.get(a.decided_by_user_id), "decided_at": a.decided_at,
        "created_at": a.created_at,
    }


async def _lookups(db: AsyncSession, company_id: uuid.UUID) -> tuple[dict, dict, dict]:
    types = {t.id: t for t in (await db.execute(select(AbsenceType).where(AbsenceType.company_id == company_id))).scalars()}
    employees = {e.id: e for e in (await db.execute(select(Employee).where(Employee.company_id == company_id))).scalars()}
    users = dict((await db.execute(select(User.id, User.full_name).where(User.company_id == company_id))).all())
    return types, employees, users


async def absence_detail(db: AsyncSession, company_id: uuid.UUID, absence_id: uuid.UUID) -> dict:
    return _absence(await _get(db, company_id, absence_id), *await _lookups(db, company_id))


async def list_absences(db: AsyncSession, company_id: uuid.UUID, date_from: date | None = None, date_to: date | None = None,
                        status: str | None = None, employee_id: uuid.UUID | None = None) -> dict:
    query = select(Absence).where(Absence.company_id == company_id)
    if date_from is not None:
        query = query.where(Absence.end_date >= date_from)
    if date_to is not None:
        query = query.where(Absence.start_date <= date_to)
    if status == "ABERTAS":
        query = query.where(Absence.status == AbsenceStatus.PEDIDA)
    elif status in AbsenceStatus.__members__:
        query = query.where(Absence.status == AbsenceStatus(status))
    if employee_id is not None:
        query = query.where(Absence.employee_id == employee_id)
    rows = (await db.execute(query.order_by(Absence.start_date.desc(), Absence.created_at.desc()))).scalars().all()
    lookups = await _lookups(db, company_id)
    pending = (await db.execute(select(Absence.id).where(Absence.company_id == company_id, Absence.status == AbsenceStatus.PEDIDA))).all()
    return {"absences": [_absence(a, *lookups) for a in rows], "pending": len(pending)}


async def absence_options(db: AsyncSession, company_id: uuid.UUID) -> dict:
    await ensure_absence_types(db, company_id)
    types = (await db.execute(select(AbsenceType).where(AbsenceType.company_id == company_id, AbsenceType.is_active.is_(True))
                              .order_by(AbsenceType.position, AbsenceType.name))).scalars().all()
    employees = (await db.execute(select(Employee).where(Employee.company_id == company_id, Employee.is_active.is_(True))
                                  .order_by(Employee.full_name))).scalars().all()
    return {"types": [{"id": t.id, "name": t.name, "category": t.category, "paid": t.paid, "working_days": t.working_days,
                       "max_days": t.max_days, "requires_document": t.requires_document} for t in types],
            "employees": [{"id": e.id, "name": e.full_name, "number": e.number} for e in employees]}


async def month_map(db: AsyncSession, company_id: uuid.UUID, year: int, month: int, department_id: uuid.UUID | None = None) -> dict:
    """The team's month: for each employee present in the month, what each day is (absence type, holiday, day off)."""
    if not (1 <= month <= 12 and 2000 <= year <= 2100):
        raise EmployeeError("Mês inválido")
    from app.services.payroll_settings_service import ensure_payroll_defaults
    first = date(year, month, 1)
    last = (date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)) - timedelta(days=1)
    settings = await ensure_payroll_defaults(db, company_id)
    weekdays = set(settings.work_weekdays or [0, 1, 2, 3, 4])
    holidays = {h.day: h.name for h in (await db.execute(select(HrHoliday).where(
        HrHoliday.company_id == company_id, HrHoliday.day >= first, HrHoliday.day <= last))).scalars()}
    days = []
    for k in range((last - first).days + 1):
        day = first + timedelta(days=k)
        days.append({"day": day, "weekday": day.weekday(), "off": day.weekday() not in weekdays, "holiday": holidays.get(day)})
    query = select(Employee).where(Employee.company_id == company_id, Employee.hired_on <= last,
                                   or_(Employee.left_on.is_(None), Employee.left_on >= first))
    if department_id is not None:
        query = query.where(Employee.department_id == department_id)
    employees = (await db.execute(query.order_by(Employee.full_name))).scalars().all()
    absences = (await db.execute(select(Absence).where(
        Absence.company_id == company_id, Absence.status.in_(LIVE), Absence.start_date <= last, Absence.end_date >= first,
        Absence.employee_id.in_([e.id for e in employees] or [uuid.uuid4()])))).scalars().all()
    types = {t.id: t for t in (await db.execute(select(AbsenceType).where(AbsenceType.company_id == company_id))).scalars()}
    rows = []
    for e in employees:
        cells = {}
        for a in (a for a in absences if a.employee_id == e.id):
            t = types.get(a.type_id)
            day = max(a.start_date, first)
            while day <= min(a.end_date, last):
                counts = (not t.working_days) or (day.weekday() in weekdays and day not in holidays)
                if counts:
                    cells[day.isoformat()] = {"absence_id": a.id, "type": t.name, "category": t.category,
                                              "pending": a.status == AbsenceStatus.PEDIDA, "half": a.half_day}
                day += timedelta(days=1)
        rows.append({"employee_id": e.id, "name": e.full_name, "number": e.number, "cells": cells,
                     "absent_days": sum(0.5 if c["half"] else 1 for c in cells.values() if not c["pending"])})
    return {"year": year, "month": month, "days": days, "employees": rows}

