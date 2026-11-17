"""
Recursos Humanos (capability HR), step 1: the employees' files and the company's HR tables.

Rules:
- the HR tables (HrReference) belong to the company; the first visit gives a starting set (contract types, education
  levels, documents of the file) that the company renames, completes or switches off - a value already used is never
  deleted, only switched off (the employee keeps it, a new file no longer offers it);
- the matrícula is proposed (0001, 0002...: the highest number + 1) and can be typed; unique per company, like the
  identity document, the NIF and the social security number when given;
- a file needs the name, the admission date and the base salary; a transfer needs the IBAN (AO06 + 21 digits, its
  check digits verified); dates make sense (born before today, document valid after its issue, contract ending after
  the admission);
- a departure keeps the file: the date (never before the admission) and the reason, the employee leaves the active
  list; a readmission brings him back with a new admission date;
- an employee may be linked to one user account of the company (one employee per account): his departure switches
  the account off (never the gestor's - the company would be locked out); a readmission does not switch it back on,
  the gestor does it in Utilizadores if he wants.
"""
import re
import uuid
from datetime import date

from sqlalchemy import func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.bank import Bank
from app.models.country import Country
from app.models.employee import (
    GENDERS, ID_DOCUMENT_TYPES, LEAVING_REASONS, MARITAL_STATUSES, PAYMENT_METHODS, REFERENCE_KINDS, Employee, HrReference,
)
from app.models.establishment import Establishment
from app.models.user import User, UserRole

# the starting set of the tables, given once per company (the departments, categories, titles and schedules are the
# company's own: they start empty)
DEFAULT_REFERENCES: dict[str, tuple[str, ...]] = {
    "TIPO_CONTRATO": ("Por tempo indeterminado", "Por tempo determinado", "Prestação de serviços", "Estágio"),
    "ESCOLARIDADE": ("Ensino primário", "I ciclo do ensino secundário", "II ciclo do ensino secundário / médio",
                     "Bacharelato", "Licenciatura", "Mestrado", "Doutoramento"),
    "TIPO_DOCUMENTO": ("Bilhete de identidade", "Cartão de contribuinte (NIF)", "Cartão de segurança social",
                       "Certificado de habilitações", "Curriculum vitae", "Atestado médico", "Contrato assinado"),
}

# HrReference columns of the file, with the kind each one takes
REFERENCE_FIELDS: dict[str, str] = {
    "department_id": "DEPARTAMENTO", "category_id": "CATEGORIA", "job_title_id": "FUNCAO",
    "contract_type_id": "TIPO_CONTRATO", "work_schedule_id": "HORARIO", "education_level_id": "ESCOLARIDADE",
}
TEXT_FIELDS: dict[str, int] = {
    "full_name": 200, "father_name": 200, "mother_name": 200, "id_document_number": 30, "nif": 20,
    "social_security_number": 20, "address": 300, "phone": 20, "email": 120, "iban": 34,
}
LONG_TEXT_FIELDS = ("training", "experience", "notes")
DATE_FIELDS = ("birth_date", "id_issued_on", "id_expires_on", "hired_on", "contract_ends_on", "probation_ends_on")


class EmployeeError(Exception):
    """Refused, with the message to show (PT-PT)."""


class EmployeeNotFoundError(EmployeeError):
    pass


# --- the HR tables -------------------------------------------------------------------------------------------------

async def ensure_default_references(db: AsyncSession, company_id: uuid.UUID) -> None:
    """The starting set, once: only a list the company has never filled gets it."""
    used = set((await db.execute(select(HrReference.kind).where(HrReference.company_id == company_id).distinct())).scalars())
    added = False
    for kind, names in DEFAULT_REFERENCES.items():
        if kind in used:
            continue
        for position, name in enumerate(names):
            db.add(HrReference(company_id=company_id, kind=kind, name=name, position=position))
        added = True
    if added:
        await db.commit()


def _reference(r: HrReference) -> dict:
    return {"id": r.id, "kind": r.kind, "name": r.name, "is_active": r.is_active, "position": r.position}


async def list_references(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """Every list, active values and switched-off ones, with how many employees use each value."""
    await ensure_default_references(db, company_id)
    rows = (await db.execute(select(HrReference).where(HrReference.company_id == company_id)
                             .order_by(HrReference.kind, HrReference.position, HrReference.name))).scalars().all()
    usage: dict[uuid.UUID, int] = {}
    for column in REFERENCE_FIELDS:
        field = getattr(Employee, column)
        for ref_id, n in (await db.execute(select(field, func.count()).where(
                Employee.company_id == company_id, field.isnot(None)).group_by(field))).all():
            usage[ref_id] = usage.get(ref_id, 0) + n
    kinds = [{"kind": k, "label": label, "values": [] } for k, label in REFERENCE_KINDS.items()]
    by_kind = {k["kind"]: k for k in kinds}
    for r in rows:
        if r.kind in by_kind:
            by_kind[r.kind]["values"].append({**_reference(r), "employees": usage.get(r.id, 0)})
    return {"kinds": kinds}


def _clean_name(name: str | None) -> str:
    name = " ".join((name or "").split())
    if not name:
        raise EmployeeError("Indique o nome")
    if len(name) > 120:
        raise EmployeeError("O nome tem no máximo 120 caracteres")
    return name


async def _name_taken(db: AsyncSession, company_id: uuid.UUID, kind: str, name: str, except_id: uuid.UUID | None = None) -> bool:
    query = select(HrReference.id).where(HrReference.company_id == company_id, HrReference.kind == kind,
                                         func.lower(HrReference.name) == name.lower())
    if except_id is not None:
        query = query.where(HrReference.id != except_id)
    return (await db.execute(query)).first() is not None


async def create_reference(db: AsyncSession, company_id: uuid.UUID, kind: str, name: str) -> dict:
    if kind not in REFERENCE_KINDS:
        raise EmployeeError("Tabela desconhecida")
    name = _clean_name(name)
    if await _name_taken(db, company_id, kind, name):
        raise EmployeeError(f"«{name}» já existe em {REFERENCE_KINDS[kind].lower()}")
    position = (await db.execute(select(func.coalesce(func.max(HrReference.position), -1)).where(
        HrReference.company_id == company_id, HrReference.kind == kind))).scalar_one() + 1
    reference = HrReference(company_id=company_id, kind=kind, name=name, position=position)
    db.add(reference)
    await db.commit()
    await db.refresh(reference)
    return _reference(reference)


async def _get_reference(db: AsyncSession, company_id: uuid.UUID, reference_id: uuid.UUID) -> HrReference:
    reference = (await db.execute(select(HrReference).where(
        HrReference.id == reference_id, HrReference.company_id == company_id))).scalar_one_or_none()
    if reference is None:
        raise EmployeeNotFoundError("Valor não encontrado")
    return reference


async def update_reference(db: AsyncSession, company_id: uuid.UUID, reference_id: uuid.UUID, name: str,
                           is_active: bool) -> dict:
    """Renamed (every file using it shows the new name) or switched off/on."""
    reference = await _get_reference(db, company_id, reference_id)
    name = _clean_name(name)
    if await _name_taken(db, company_id, reference.kind, name, reference.id):
        raise EmployeeError(f"«{name}» já existe em {REFERENCE_KINDS[reference.kind].lower()}")
    reference.name, reference.is_active = name, bool(is_active)
    await db.commit()
    await db.refresh(reference)
    return _reference(reference)


async def delete_reference(db: AsyncSession, company_id: uuid.UUID, reference_id: uuid.UUID) -> None:
    """Only a value no file uses: one in use is switched off instead (the employee keeps it)."""
    reference = await _get_reference(db, company_id, reference_id)
    column = next((c for c, k in REFERENCE_FIELDS.items() if k == reference.kind), None)
    if column is not None:
        used = (await db.execute(select(func.count()).select_from(Employee).where(
            Employee.company_id == company_id, getattr(Employee, column) == reference.id))).scalar_one()
        if used:
            raise EmployeeError(f"«{reference.name}» está na ficha de {used} colaborador(es): desative-o em vez de o apagar")
    await db.delete(reference)
    await db.commit()


# --- the employees -------------------------------------------------------------------------------------------------

async def next_number(db: AsyncSession, company_id: uuid.UUID) -> str:
    """The highest numeric matrícula + 1, on 4 digits (0001 for the first employee)."""
    numbers = (await db.execute(select(Employee.number).where(Employee.company_id == company_id))).scalars().all()
    highest = max((int(n) for n in numbers if n.isdigit()), default=0)
    return str(highest + 1).zfill(4)


async def employee_options(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """What the file offers: the active values of each HR table, the countries, banks and establishments, the fixed
    lists, and the next matrícula."""
    await ensure_default_references(db, company_id)
    references = (await db.execute(select(HrReference).where(HrReference.company_id == company_id)
                                   .order_by(HrReference.position, HrReference.name))).scalars().all()
    tables = {kind: [] for kind in REFERENCE_KINDS}
    for r in references:
        if r.kind in tables:
            tables[r.kind].append({"id": r.id, "name": r.name, "is_active": r.is_active})
    countries = (await db.execute(select(Country).where(Country.is_active.is_(True)).order_by(Country.name))).scalars().all()
    banks = (await db.execute(select(Bank).where(Bank.is_active.is_(True)).order_by(Bank.acronym))).scalars().all()
    establishments = (await db.execute(select(Establishment).where(
        Establishment.company_id == company_id, Establishment.is_active.is_(True)).order_by(Establishment.name))).scalars().all()
    pairs = lambda d: [{"value": k, "label": v} for k, v in d.items()]  # noqa: E731
    return {
        "tables": tables,
        "countries": [{"id": c.id, "code": c.code, "name": c.name} for c in countries],
        "banks": [{"id": b.id, "name": f"{b.acronym} - {b.full_name}"} for b in banks],
        "establishments": [{"id": e.id, "name": e.name} for e in establishments],
        "genders": pairs(GENDERS), "marital_statuses": pairs(MARITAL_STATUSES), "id_document_types": pairs(ID_DOCUMENT_TYPES),
        "payment_methods": pairs(PAYMENT_METHODS), "leaving_reasons": pairs(LEAVING_REASONS),
        "next_number": await next_number(db, company_id),
        "users": await _linkable_users(db, company_id),
    }


async def _linkable_users(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """The company's accounts, with the employee each is already linked to."""
    users = (await db.execute(select(User).where(User.company_id == company_id).order_by(User.full_name))).scalars().all()
    linked = dict((await db.execute(select(Employee.user_id, Employee.id).where(
        Employee.company_id == company_id, Employee.user_id.isnot(None)))).all())
    return [{"id": u.id, "name": u.full_name, "phone": u.phone_number, "role": u.role.value, "is_active": u.is_active,
             "employee_id": linked.get(u.id)} for u in users]


def _iban_ok(iban: str) -> bool:
    """ISO 13616 check digits (mod 97); an Angolan IBAN is AO06 followed by 21 digits."""
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    if iban.startswith("AO") and not re.fullmatch(r"AO\d{23}", iban):
        return False
    digits = "".join(str(int(ch, 36)) for ch in iban[4:] + iban[:4])
    return int(digits) % 97 == 1


def _text(value, limit: int, label: str) -> str | None:
    value = " ".join(str(value).split()) if value is not None else ""
    if len(value) > limit:
        raise EmployeeError(f"{label}: no máximo {limit} caracteres")
    return value or None


def _date(value, label: str) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        raise EmployeeError(f"{label}: data inválida")


LABELS = {
    "full_name": "Nome completo", "father_name": "Nome do pai", "mother_name": "Nome da mãe",
    "id_document_number": "N.º do documento", "nif": "NIF", "social_security_number": "N.º de segurança social",
    "address": "Morada", "phone": "Telefone", "email": "Email", "iban": "IBAN", "birth_date": "Data de nascimento",
    "id_issued_on": "Data de emissão do documento", "id_expires_on": "Validade do documento", "hired_on": "Data de admissão",
    "contract_ends_on": "Fim do contrato", "probation_ends_on": "Fim do período experimental",
}


async def _check(db: AsyncSession, company_id: uuid.UUID, data: dict, current: Employee | None) -> dict:
    """The file's values, cleaned and checked - EmployeeError with the first problem."""
    clean: dict = {}
    for field, limit in TEXT_FIELDS.items():
        clean[field] = _text(data.get(field), limit, LABELS[field])
    for field in LONG_TEXT_FIELDS:
        value = (data.get(field) or "").strip()
        clean[field] = value or None
    for field in DATE_FIELDS:
        clean[field] = _date(data.get(field), LABELS[field])

    if not clean["full_name"]:
        raise EmployeeError("Indique o nome completo do colaborador")
    number = _text(data.get("number"), 20, "Matrícula")
    clean["number"] = number or await next_number(db, company_id)
    if clean["nif"]:
        clean["nif"] = clean["nif"].replace(" ", "").upper()
    if clean["id_document_number"]:
        clean["id_document_number"] = clean["id_document_number"].replace(" ", "").upper()
    if clean["email"] and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", clean["email"]):
        raise EmployeeError("Email inválido")

    for field, choices, label in (("gender", GENDERS, "Género"), ("marital_status", MARITAL_STATUSES, "Estado civil"),
                                  ("id_document_type", ID_DOCUMENT_TYPES, "Tipo de documento")):
        value = data.get(field) or None
        if value is not None and value not in choices:
            raise EmployeeError(f"{label} inválido")
        clean[field] = value
    if clean["id_document_number"] and not clean["id_document_type"]:
        clean["id_document_type"] = "BI"

    today = date.today()
    if clean["birth_date"] and clean["birth_date"] >= today:
        raise EmployeeError("A data de nascimento tem de ser anterior a hoje")
    if clean["id_issued_on"] and clean["id_expires_on"] and clean["id_expires_on"] < clean["id_issued_on"]:
        raise EmployeeError("A validade do documento é anterior à data de emissão")
    if not clean["hired_on"]:
        raise EmployeeError("Indique a data de admissão")
    if clean["birth_date"] and clean["hired_on"] <= clean["birth_date"]:
        raise EmployeeError("A data de admissão é anterior à data de nascimento")
    for field in ("contract_ends_on", "probation_ends_on"):
        if clean[field] and clean[field] < clean["hired_on"]:
            raise EmployeeError(f"{LABELS[field]} é anterior à data de admissão")

    # the HR tables: a value of the company, of the right list - an inactive one only if the file already has it
    for field, kind in REFERENCE_FIELDS.items():
        value = data.get(field) or None
        if value is not None:
            reference = (await db.execute(select(HrReference).where(
                HrReference.id == value, HrReference.company_id == company_id, HrReference.kind == kind))).scalar_one_or_none()
            if reference is None:
                raise EmployeeError(f"{REFERENCE_KINDS[kind]}: valor inválido")
            if not reference.is_active and (current is None or getattr(current, field) != reference.id):
                raise EmployeeError(f"«{reference.name}» está desativado em {REFERENCE_KINDS[kind].lower()}")
            value = reference.id
        clean[field] = value
    nationality = data.get("nationality_id") or None
    if nationality is not None and (await db.get(Country, nationality)) is None:
        raise EmployeeError("Nacionalidade inválida")
    clean["nationality_id"] = nationality
    establishment = data.get("establishment_id") or None
    if establishment is not None and (await db.execute(select(Establishment.id).where(
            Establishment.id == establishment, Establishment.company_id == company_id))).first() is None:
        raise EmployeeError("Local de trabalho inválido")
    clean["establishment_id"] = establishment

    # pay
    try:
        salary = round(float(data.get("base_salary")), 2)
    except (TypeError, ValueError):
        salary = 0
    if salary <= 0:
        raise EmployeeError("Indique o salário base")
    clean["base_salary"] = salary
    method = data.get("payment_method") or "TRANSFERENCIA"
    if method not in PAYMENT_METHODS:
        raise EmployeeError("Forma de pagamento inválida")
    clean["payment_method"] = method
    if clean["iban"]:
        clean["iban"] = "".join(clean["iban"].split()).upper()
        if not _iban_ok(clean["iban"]):
            raise EmployeeError("IBAN inválido (Angola: AO06 seguido de 21 algarismos)")
    if method == "TRANSFERENCIA" and not clean["iban"]:
        raise EmployeeError("Uma transferência bancária precisa do IBAN do colaborador")
    bank = data.get("bank_id") or None
    if bank is not None and (await db.get(Bank, bank)) is None:
        raise EmployeeError("Banco inválido")
    clean["bank_id"] = bank

    # his account: one of the company, not already another employee's
    account = data.get("user_id") or None
    if account is not None:
        user = (await db.execute(select(User).where(User.id == account, User.company_id == company_id))).scalar_one_or_none()
        if user is None:
            raise EmployeeError("Conta de utilizador inválida")
        other = (await db.execute(select(Employee.full_name).where(
            Employee.user_id == user.id, *([Employee.id != current.id] if current is not None else [])))).scalar_one_or_none()
        if other is not None:
            raise EmployeeError(f"A conta de {user.full_name} já está ligada a {other}")
        account = user.id
    clean["user_id"] = account

    # unique per company
    exclude = [Employee.id != current.id] if current is not None else []
    for field, label, value in (
            ("number", "a matrícula", clean["number"]), ("id_document_number", "o documento de identificação", clean["id_document_number"]),
            ("nif", "o NIF", clean["nif"]), ("social_security_number", "o n.º de segurança social", clean["social_security_number"])):
        if not value:
            continue
        column = getattr(Employee, field)
        other = (await db.execute(select(Employee.full_name).where(
            Employee.company_id == company_id, func.lower(column) == value.lower(), *exclude))).scalar_one_or_none()
        if other is not None:
            raise EmployeeError(f"{other} já tem {label} {value}")
    return clean


async def get_employee(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> Employee:
    employee = (await db.execute(select(Employee).where(
        Employee.id == employee_id, Employee.company_id == company_id))).scalar_one_or_none()
    if employee is None:
        raise EmployeeNotFoundError("Colaborador não encontrado")
    return employee


async def _names(db: AsyncSession, company_id: uuid.UUID) -> dict:
    refs = dict((await db.execute(select(HrReference.id, HrReference.name).where(HrReference.company_id == company_id))).all())
    countries = dict((await db.execute(select(Country.id, Country.name))).all())
    banks = dict((await db.execute(select(Bank.id, Bank.acronym))).all())
    establishments = dict((await db.execute(select(Establishment.id, Establishment.name).where(
        Establishment.company_id == company_id))).all())
    users = dict((await db.execute(select(User.id, User.full_name).where(User.company_id == company_id))).all())
    return {"refs": refs, "countries": countries, "banks": banks, "establishments": establishments, "users": users}


def _employee(e: Employee, names: dict) -> dict:
    refs = names["refs"]
    out = {c.name: getattr(e, c.name) for c in Employee.__table__.columns if c.name not in ("company_id", "created_by_user_id")}
    out["base_salary"] = float(e.base_salary)
    out.update({
        "department": refs.get(e.department_id), "category": refs.get(e.category_id), "job_title": refs.get(e.job_title_id),
        "contract_type": refs.get(e.contract_type_id), "work_schedule": refs.get(e.work_schedule_id),
        "education_level": refs.get(e.education_level_id), "nationality": names["countries"].get(e.nationality_id),
        "bank": names["banks"].get(e.bank_id), "establishment": names["establishments"].get(e.establishment_id),
        "leaving_reason_label": LEAVING_REASONS.get(e.leaving_reason), "user_name": names["users"].get(e.user_id),
        "has_photo": e.id in names.get("photos", ()),
    })
    return out


async def employee_detail(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> dict:
    from app.services.employee_file_service import has_photo
    names = await _names(db, company_id)
    names["photos"] = await has_photo(db, [employee_id])
    return _employee(await get_employee(db, company_id, employee_id), names)


async def create_employee(db: AsyncSession, company_id: uuid.UUID, user_id: uuid.UUID | None, data: dict) -> dict:
    # two people creating a file at once never get the same proposed matrícula
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"employees:{company_id}"})
    clean = await _check(db, company_id, data, None)
    employee = Employee(company_id=company_id, created_by_user_id=user_id, **clean)
    db.add(employee)
    await db.commit()
    return await employee_detail(db, company_id, employee.id)


async def update_employee(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, data: dict) -> dict:
    employee = await get_employee(db, company_id, employee_id)
    clean = await _check(db, company_id, data, employee)
    if employee.left_on and clean["hired_on"] > employee.left_on:
        raise EmployeeError("A data de admissão é posterior à data de saída")
    for field, value in clean.items():
        setattr(employee, field, value)
    await db.commit()
    return await employee_detail(db, company_id, employee_id)


async def register_departure(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, left_on, reason: str,
                             note: str | None = None) -> dict:
    """The employee leaves: the file stays, out of the active list."""
    employee = await get_employee(db, company_id, employee_id)
    if not employee.is_active:
        raise EmployeeError(f"{employee.full_name} já saiu da empresa")
    left_on = _date(left_on, "Data de saída")
    if left_on is None:
        raise EmployeeError("Indique a data de saída")
    if left_on < employee.hired_on:
        raise EmployeeError("A data de saída é anterior à data de admissão")
    if reason not in LEAVING_REASONS:
        raise EmployeeError("Escolha o motivo da saída")
    note = _text(note, 300, "Observação")
    if reason == "OUTRO" and not note:
        raise EmployeeError("Descreva o motivo da saída")
    employee.is_active, employee.left_on, employee.leaving_reason, employee.leaving_note = False, left_on, reason, note
    # his account closes with him (never the gestor's: nobody could open the company any more)
    account_closed = False
    if employee.user_id is not None:
        user = await db.get(User, employee.user_id)
        if user is not None and user.is_active and user.role != UserRole.GESTOR:
            user.is_active, account_closed = False, True
    await db.commit()
    return {**await employee_detail(db, company_id, employee_id), "account_closed": account_closed}


async def readmit_employee(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, hired_on) -> dict:
    """Back in the company, with a new admission date (after the departure)."""
    employee = await get_employee(db, company_id, employee_id)
    if employee.is_active:
        raise EmployeeError(f"{employee.full_name} está ativo")
    hired_on = _date(hired_on, "Data de readmissão")
    if hired_on is None:
        raise EmployeeError("Indique a data de readmissão")
    if employee.left_on and hired_on <= employee.left_on:
        raise EmployeeError("A readmissão tem de ser posterior à data de saída")
    employee.is_active, employee.hired_on = True, hired_on
    employee.left_on = employee.leaving_reason = employee.leaving_note = None
    employee.contract_ends_on = employee.probation_ends_on = None
    await db.commit()
    return await employee_detail(db, company_id, employee_id)


async def list_employees(db: AsyncSession, company_id: uuid.UUID, status: str = "ATIVOS", search: str | None = None,
                         department_id: uuid.UUID | None = None) -> dict:
    """The employees (active, gone or all), by matrícula - with the counts for the filter's tabs."""
    query = select(Employee).where(Employee.company_id == company_id)
    if status == "ATIVOS":
        query = query.where(Employee.is_active.is_(True))
    elif status == "SAIDOS":
        query = query.where(Employee.is_active.is_(False))
    if department_id is not None:
        query = query.where(Employee.department_id == department_id)
    if search and search.strip():
        q = f"%{search.strip().lower()}%"
        query = query.where(or_(func.lower(Employee.full_name).like(q), func.lower(Employee.number).like(q),
                                func.lower(func.coalesce(Employee.nif, "")).like(q),
                                func.lower(func.coalesce(Employee.id_document_number, "")).like(q),
                                func.coalesce(Employee.phone, "").like(q)))
    rows = (await db.execute(query.order_by(Employee.number))).scalars().all()
    from app.services.employee_file_service import has_photo
    names = await _names(db, company_id)
    names["photos"] = await has_photo(db, [e.id for e in rows])
    counts = dict((await db.execute(select(Employee.is_active, func.count()).where(
        Employee.company_id == company_id).group_by(Employee.is_active))).all())
    return {"employees": [_employee(e, names) for e in rows],
            "counts": {"ATIVOS": counts.get(True, 0), "SAIDOS": counts.get(False, 0),
                       "TODOS": counts.get(True, 0) + counts.get(False, 0)}}
