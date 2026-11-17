"""
Recursos Humanos, step 2: the payroll settings - INSS, the IRT tables, the rubricas, the rubricas of each employee -
and the payslip simulation that reads them (the monthly calculation of step 4 uses the same compute_payslip).

Nothing of the law is in the code: the rates, the IRT brackets, which rubrica enters which base and its exempt part
are the company's settings, given a starting set once (the values in force on 17/11/2026, to be confirmed by the
company's accountant) and changed on the screen.

The payslip:
- gross = base salary + the allowances;
- INSS base = base salary + the allowances «entra na base do INSS» - the deductions «reduz a base do INSS»;
  employee INSS = base x employee rate, employer INSS = base x employer rate;
- IRT base = base salary + the taxable part of the allowances «entra na base do IRT» (above their exempt limit)
  - the deductions «reduz a base do IRT» - the employee INSS (if so set); IRT = the table valid at the payslip's
  date: fixed amount + (base - «applied above») x rate, in the bracket of the base;
- net = gross - employee INSS - IRT - the deductions.
"""
import re
import uuid
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.employee import Employee
from app.models.payroll import CALC_METHODS, NATURES, EmployeePayrollItem, IrtTable, PayrollItem, PayrollSettings
from app.services.employee_service import EmployeeError, EmployeeNotFoundError, get_employee
from app.services.payroll_formula import FUNCTIONS, FormulaError, evaluate, parse, variables

# OGE 2026 (Lei n.º 14/25): exempt up to 150 000 Kz - the starting table, editable
DEFAULT_IRT_TABLE = {
    "name": "OGE 2026 - Lei n.º 14/25",
    "valid_from": date(2026, 1, 1),
    "brackets": [
        {"from": 0, "to": 150000, "fixed": 0, "rate": 0, "over": 0},
        {"from": 150000, "to": 200000, "fixed": 12500, "rate": 16, "over": 150000},
        {"from": 200000, "to": 300000, "fixed": 31250, "rate": 18, "over": 200000},
        {"from": 300000, "to": 500000, "fixed": 49250, "rate": 19, "over": 300000},
        {"from": 500000, "to": 1000000, "fixed": 87250, "rate": 20, "over": 500000},
        {"from": 1000000, "to": 1500000, "fixed": 187250, "rate": 21, "over": 1000000},
        {"from": 1500000, "to": 2000000, "fixed": 292250, "rate": 22, "over": 1500000},
        {"from": 2000000, "to": 2500000, "fixed": 402250, "rate": 23, "over": 2000000},
        {"from": 2500000, "to": 5000000, "fixed": 517250, "rate": 24, "over": 2500000},
        {"from": 5000000, "to": 10000000, "fixed": 1117250, "rate": 24.5, "over": 5000000},
        {"from": 10000000, "to": None, "fixed": 2342250, "rate": 25, "over": 10000000},
    ],
}

# the starting rubricas: (code, name, nature, method, inss, irt, exempt limit, notes)
DEFAULT_ITEMS = (
    ("SUB_ALIM", "Subsídio de alimentação", "ABONO", "FIXO", True, True, 30000, "Isento de IRT até 30 000 Kz: o excedente é tributado"),
    ("SUB_TRANSP", "Subsídio de transporte", "ABONO", "FIXO", True, True, 30000, "Isento de IRT até 30 000 Kz: o excedente é tributado"),
    ("HORAS_EXTRA", "Horas extraordinárias", "ABONO", "MENSAL", True, True, None, None),
    ("PREMIO", "Prémio", "ABONO", "MENSAL", True, True, None, None),
    ("SUB_FERIAS", "Subsídio de férias", "ABONO", "MENSAL", True, True, None, None),
    ("SUB_NATAL", "Subsídio de Natal", "ABONO", "MENSAL", True, True, None, None),
    ("FALTAS", "Faltas injustificadas", "DESCONTO", "MENSAL", True, True, None, "Reduz a base do INSS e do IRT"),
    ("ADIANT", "Adiantamento", "DESCONTO", "MENSAL", False, False, None, "Já pago: não altera as bases"),
)

# the variables every formula can read (besides the codes of the rubricas)
BUILTIN_VARIABLES = {
    "SB": "Salário base",
    "HORAS_MES": "Horas de trabalho num mês (parâmetros)",
    "DIAS_MES": "Dias de trabalho num mês (parâmetros)",
    "VH": "Valor da hora: SB / HORAS_MES",
    "VD": "Valor do dia: SB / DIAS_MES",
    "ANTIGUIDADE": "Anos completos de antiguidade na data do recibo",
}
CODE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,19}$")


def round2(value: float) -> float:
    return float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


class PayrollError(EmployeeError):
    """Refused, with the message to show (PT-PT)."""


# --- the starting set --------------------------------------------------------------------------------------------

async def ensure_payroll_defaults(db: AsyncSession, company_id: uuid.UUID) -> PayrollSettings:
    """The settings, the IRT table and the rubricas of a company that has none yet - once."""
    settings = (await db.execute(select(PayrollSettings).where(PayrollSettings.company_id == company_id))).scalar_one_or_none()
    if settings is not None:
        return settings
    await db.execute(text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"payroll-defaults:{company_id}"})
    settings = (await db.execute(select(PayrollSettings).where(PayrollSettings.company_id == company_id))).scalar_one_or_none()
    if settings is not None:
        return settings
    settings = PayrollSettings(company_id=company_id, inss_employee_rate=3, inss_employer_rate=8, monthly_hours=190.66,
                               monthly_days=22, inss_deducted_from_irt=True)
    db.add(settings)
    if not (await db.execute(select(IrtTable.id).where(IrtTable.company_id == company_id))).first():
        db.add(IrtTable(company_id=company_id, **DEFAULT_IRT_TABLE))
    if not (await db.execute(select(PayrollItem.id).where(PayrollItem.company_id == company_id))).first():
        for position, (code, name, nature, method, inss, irt, limit, notes) in enumerate(DEFAULT_ITEMS):
            db.add(PayrollItem(company_id=company_id, code=code, name=name, nature=nature, calc_method=method, subject_inss=inss,
                               subject_irt=irt, irt_exempt_limit=limit, notes=notes, position=position))
    await db.commit()
    await db.refresh(settings)
    return settings


# --- the general settings ----------------------------------------------------------------------------------------

def _settings(s: PayrollSettings) -> dict:
    return {"inss_employee_rate": float(s.inss_employee_rate), "inss_employer_rate": float(s.inss_employer_rate),
            "monthly_hours": float(s.monthly_hours), "monthly_days": float(s.monthly_days),
            "inss_deducted_from_irt": s.inss_deducted_from_irt}


def _number(value, label: str, low: float = 0, high: float | None = None, allow_low: bool = True) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise PayrollError(f"{label}: indique um número")
    if number < low or (number == low and not allow_low) or (high is not None and number > high):
        raise PayrollError(f"{label}: valor fora dos limites")
    return number


async def get_payroll_settings(db: AsyncSession, company_id: uuid.UUID) -> dict:
    return _settings(await ensure_payroll_defaults(db, company_id))


async def update_payroll_settings(db: AsyncSession, company_id: uuid.UUID, data: dict) -> dict:
    s = await ensure_payroll_defaults(db, company_id)
    s.inss_employee_rate = _number(data.get("inss_employee_rate"), "INSS do trabalhador (%)", 0, 100)
    s.inss_employer_rate = _number(data.get("inss_employer_rate"), "INSS da entidade empregadora (%)", 0, 100)
    s.monthly_hours = _number(data.get("monthly_hours"), "Horas por mês", 0, 744, allow_low=False)
    s.monthly_days = _number(data.get("monthly_days"), "Dias por mês", 0, 31, allow_low=False)
    s.inss_deducted_from_irt = bool(data.get("inss_deducted_from_irt", True))
    await db.commit()
    await db.refresh(s)
    return _settings(s)


# --- the IRT tables ----------------------------------------------------------------------------------------------

def _table(t: IrtTable) -> dict:
    return {"id": t.id, "name": t.name, "valid_from": t.valid_from, "brackets": t.brackets}


def _clean_brackets(rows) -> list[dict]:
    """The brackets in order, without gap or overlap: each starts where the previous ends, only the last has no end."""
    if not rows:
        raise PayrollError("A tabela precisa de pelo menos um escalão")
    out = []
    for k, row in enumerate(rows, start=1):
        start = _number(row.get("from"), f"Escalão {k}: de", 0)
        end = row.get("to")
        end = None if end in (None, "") else _number(end, f"Escalão {k}: até", 0)
        out.append({"from": start, "to": end, "fixed": _number(row.get("fixed") or 0, f"Escalão {k}: parcela fixa", 0),
                    "rate": _number(row.get("rate") or 0, f"Escalão {k}: taxa (%)", 0, 100),
                    "over": _number(row.get("over") if row.get("over") not in (None, "") else start, f"Escalão {k}: excesso de", 0)})
    out.sort(key=lambda b: b["from"])
    if out[0]["from"] != 0:
        raise PayrollError("O primeiro escalão começa em 0")
    for k, (a, b) in enumerate(zip(out, out[1:]), start=1):
        if a["to"] is None or a["to"] != b["from"]:
            raise PayrollError(f"O escalão {k} tem de acabar onde começa o escalão {k + 1}")
        if a["to"] <= a["from"]:
            raise PayrollError(f"O escalão {k} acaba antes de começar")
    if out[-1]["to"] is not None:
        raise PayrollError("O último escalão não tem limite superior (deixe «até» vazio)")
    return out


async def list_irt_tables(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    await ensure_payroll_defaults(db, company_id)
    rows = (await db.execute(select(IrtTable).where(IrtTable.company_id == company_id)
                             .order_by(IrtTable.valid_from.desc()))).scalars().all()
    today = date.today()
    current = next((t.id for t in rows if t.valid_from <= today), None)
    return [{**_table(t), "in_force": t.id == current} for t in rows]


async def save_irt_table(db: AsyncSession, company_id: uuid.UUID, table_id: uuid.UUID | None, data: dict) -> dict:
    name = " ".join((data.get("name") or "").split())[:120]
    if not name:
        raise PayrollError("Indique o nome da tabela (ex.: OGE 2027)")
    valid_from = data.get("valid_from")
    if isinstance(valid_from, str):
        valid_from = date.fromisoformat(valid_from)
    if not isinstance(valid_from, date):
        raise PayrollError("Indique a data a partir da qual a tabela se aplica")
    brackets = _clean_brackets(data.get("brackets") or [])
    query = select(IrtTable.id).where(IrtTable.company_id == company_id, IrtTable.valid_from == valid_from)
    if table_id is not None:
        query = query.where(IrtTable.id != table_id)
    if (await db.execute(query)).first():
        raise PayrollError(f"Já existe uma tabela de IRT a partir de {valid_from:%d/%m/%Y}")
    if table_id is None:
        table = IrtTable(company_id=company_id, name=name, valid_from=valid_from, brackets=brackets)
        db.add(table)
    else:
        table = (await db.execute(select(IrtTable).where(IrtTable.id == table_id, IrtTable.company_id == company_id))).scalar_one_or_none()
        if table is None:
            raise EmployeeNotFoundError("Tabela não encontrada")
        table.name, table.valid_from, table.brackets = name, valid_from, brackets
    await db.commit()
    await db.refresh(table)
    return _table(table)


async def delete_irt_table(db: AsyncSession, company_id: uuid.UUID, table_id: uuid.UUID) -> None:
    table = (await db.execute(select(IrtTable).where(IrtTable.id == table_id, IrtTable.company_id == company_id))).scalar_one_or_none()
    if table is None:
        raise EmployeeNotFoundError("Tabela não encontrada")
    if (await db.execute(select(func.count()).select_from(IrtTable).where(IrtTable.company_id == company_id))).scalar_one() == 1:
        raise PayrollError("A empresa precisa de pelo menos uma tabela de IRT")
    await db.delete(table)
    await db.commit()


def irt_of(base: float, brackets: list[dict]) -> float:
    """The IRT of a taxable base: in its bracket, fixed amount + (base - applied above) x rate."""
    if base <= 0:
        return 0.0
    for b in sorted(brackets, key=lambda x: x["from"], reverse=True):
        if base > b["from"]:
            return round2(max(0.0, float(b["fixed"]) + (base - float(b["over"])) * float(b["rate"]) / 100))
    return 0.0


async def irt_table_on(db: AsyncSession, company_id: uuid.UUID, day: date) -> IrtTable | None:
    return (await db.execute(select(IrtTable).where(IrtTable.company_id == company_id, IrtTable.valid_from <= day)
                             .order_by(IrtTable.valid_from.desc()).limit(1))).scalar_one_or_none()


# --- the rubricas ------------------------------------------------------------------------------------------------

def _item(i: PayrollItem, usage: dict | None = None) -> dict:
    return {"id": i.id, "code": i.code, "name": i.name, "nature": i.nature, "calc_method": i.calc_method,
            "calc_label": CALC_METHODS.get(i.calc_method), "amount": None if i.amount is None else float(i.amount),
            "rate": None if i.rate is None else float(i.rate), "formula": i.formula, "subject_inss": i.subject_inss,
            "subject_irt": i.subject_irt, "irt_exempt_limit": None if i.irt_exempt_limit is None else float(i.irt_exempt_limit),
            "applies_to_all": i.applies_to_all, "is_active": i.is_active, "position": i.position, "notes": i.notes,
            "employees": (usage or {}).get(i.id, 0)}


async def list_items(db: AsyncSession, company_id: uuid.UUID) -> dict:
    await ensure_payroll_defaults(db, company_id)
    rows = (await db.execute(select(PayrollItem).where(PayrollItem.company_id == company_id)
                             .order_by(PayrollItem.position, PayrollItem.code))).scalars().all()
    usage = dict((await db.execute(select(EmployeePayrollItem.item_id, func.count()).where(
        EmployeePayrollItem.company_id == company_id).group_by(EmployeePayrollItem.item_id))).all())
    return {"items": [_item(i, usage) for i in rows], "variables": [{"code": k, "label": v} for k, v in BUILTIN_VARIABLES.items()],
            "natures": [{"value": k, "label": v} for k, v in NATURES.items()],
            "calc_methods": [{"value": k, "label": v} for k, v in CALC_METHODS.items()]}


def _dependency_order(items: list[PayrollItem]) -> list[PayrollItem]:
    """The rubricas so that a formula comes after the rubricas it reads - PayrollError on a loop."""
    by_code = {i.code: i for i in items}
    order, state = [], {}

    def visit(item, path):
        if state.get(item.code) == "done":
            return
        if state.get(item.code) == "visiting":
            raise PayrollError("As fórmulas formam um ciclo: " + " → ".join(path + [item.code]))
        state[item.code] = "visiting"
        if item.calc_method == "FORMULA" and item.formula_ast:
            for code in sorted(variables(item.formula_ast)):
                if code in by_code:
                    visit(by_code[code], path + [item.code])
        state[item.code] = "done"
        order.append(item)

    for item in items:
        visit(item, [])
    return order


async def _check_item(db: AsyncSession, company_id: uuid.UUID, data: dict, current: PayrollItem | None) -> dict:
    code = (data.get("code") or "").strip().upper()
    if not CODE_RE.match(code):
        raise PayrollError("Código: 2 a 20 letras maiúsculas, algarismos ou _, a começar por uma letra (ex.: SUB_ALIM)")
    if code in BUILTIN_VARIABLES or code in FUNCTIONS:
        raise PayrollError(f"«{code}» é reservado: escolha outro código")
    others = (await db.execute(select(PayrollItem).where(PayrollItem.company_id == company_id))).scalars().all()
    others = [o for o in others if current is None or o.id != current.id]
    if any(o.code.upper() == code for o in others):
        raise PayrollError(f"Já existe uma rubrica com o código {code}")
    if current is not None and current.code != code:
        users = [o.code for o in others if o.formula_ast and current.code in variables(o.formula_ast)]
        if users:
            raise PayrollError(f"O código {current.code} é usado na fórmula de {', '.join(users)}: altere-a antes")
    name = " ".join((data.get("name") or "").split())[:120]
    if not name:
        raise PayrollError("Indique o nome da rubrica")
    nature = data.get("nature")
    if nature not in NATURES:
        raise PayrollError("Escolha abono ou desconto")
    method = data.get("calc_method")
    if method not in CALC_METHODS:
        raise PayrollError("Escolha a forma de cálculo")
    clean = {"code": code, "name": name, "nature": nature, "calc_method": method, "amount": None, "rate": None,
             "formula": None, "formula_ast": None, "subject_inss": bool(data.get("subject_inss")),
             "subject_irt": bool(data.get("subject_irt")), "irt_exempt_limit": None,
             "applies_to_all": bool(data.get("applies_to_all")) and method != "MENSAL",
             "is_active": bool(data.get("is_active", True)),
             "notes": " ".join((data.get("notes") or "").split())[:300] or None}
    if method == "FIXO" and data.get("amount") not in (None, ""):
        clean["amount"] = round2(_number(data.get("amount"), "Valor", 0))
    if method == "PERCENTAGEM":
        clean["rate"] = _number(data.get("rate"), "Percentagem do salário base", 0, 1000, allow_low=False)
    if method == "FORMULA":
        try:
            ast = parse(data.get("formula") or "")
        except FormulaError as e:
            raise PayrollError(f"Fórmula: {e}")
        known = set(BUILTIN_VARIABLES) | {o.code for o in others}
        unknown = sorted(variables(ast) - known)
        if code in variables(ast):
            raise PayrollError("Uma fórmula não pode usar a sua própria rubrica")
        if unknown:
            raise PayrollError("Fórmula: variável desconhecida " + ", ".join(unknown))
        clean["formula"], clean["formula_ast"] = " ".join((data.get("formula") or "").split()), ast
        candidate = PayrollItem(code=code, calc_method="FORMULA", formula_ast=ast)
        _dependency_order(others + [candidate])
    if nature == "ABONO" and clean["subject_irt"] and data.get("irt_exempt_limit") not in (None, ""):
        clean["irt_exempt_limit"] = round2(_number(data.get("irt_exempt_limit"), "Limite isento de IRT", 0))
    if clean["applies_to_all"] and method == "FIXO" and clean["amount"] is None:
        raise PayrollError("Uma rubrica de valor fixo para todos precisa do valor")
    return clean


async def _get_item(db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID) -> PayrollItem:
    item = (await db.execute(select(PayrollItem).where(PayrollItem.id == item_id, PayrollItem.company_id == company_id))).scalar_one_or_none()
    if item is None:
        raise EmployeeNotFoundError("Rubrica não encontrada")
    return item


async def create_item(db: AsyncSession, company_id: uuid.UUID, data: dict) -> dict:
    await ensure_payroll_defaults(db, company_id)
    clean = await _check_item(db, company_id, data, None)
    position = (await db.execute(select(func.coalesce(func.max(PayrollItem.position), -1)).where(
        PayrollItem.company_id == company_id))).scalar_one() + 1
    item = PayrollItem(company_id=company_id, position=position, **clean)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return _item(item)


async def update_item(db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID, data: dict) -> dict:
    item = await _get_item(db, company_id, item_id)
    clean = await _check_item(db, company_id, data, item)
    if clean["calc_method"] == "MENSAL" and item.calc_method != "MENSAL":
        given = (await db.execute(select(func.count()).select_from(EmployeePayrollItem).where(
            EmployeePayrollItem.item_id == item.id))).scalar_one()
        if given:
            raise PayrollError(f"A rubrica está na ficha de {given} colaborador(es): retire-a antes de a tornar mensal")
    for field, value in clean.items():
        setattr(item, field, value)
    await db.commit()
    await db.refresh(item)
    return _item(item)


async def delete_item(db: AsyncSession, company_id: uuid.UUID, item_id: uuid.UUID) -> None:
    """Only a rubrica nobody has and no formula reads: otherwise it is switched off."""
    item = await _get_item(db, company_id, item_id)
    given = (await db.execute(select(func.count()).select_from(EmployeePayrollItem).where(
        EmployeePayrollItem.item_id == item.id))).scalar_one()
    if given:
        raise PayrollError(f"A rubrica está na ficha de {given} colaborador(es): desative-a em vez de a apagar")
    readers = [o.code for o in (await db.execute(select(PayrollItem).where(
        PayrollItem.company_id == company_id, PayrollItem.id != item.id))).scalars() if o.formula_ast and item.code in variables(o.formula_ast)]
    if readers:
        raise PayrollError(f"O código {item.code} é usado na fórmula de {', '.join(readers)}")
    await db.delete(item)
    await db.commit()


async def check_formula(db: AsyncSession, company_id: uuid.UUID, formula: str, code: str | None = None,
                        salary: float = 100000) -> dict:
    """A formula read and computed on an example: base salary 100 000, 5 years of seniority, the other rubricas at their
    default amount, rate or formula (the ones typed each month at 0)."""
    try:
        ast = parse(formula)
    except FormulaError as e:
        raise PayrollError(str(e))
    others = [i for i in (await db.execute(select(PayrollItem).where(PayrollItem.company_id == company_id))).scalars()
              if i.code != (code or "").upper()]
    unknown = sorted(variables(ast) - set(BUILTIN_VARIABLES) - {i.code for i in others})
    if unknown:
        raise PayrollError("Variável desconhecida: " + ", ".join(unknown))
    s = await ensure_payroll_defaults(db, company_id)
    context = {**_builtins(salary, float(s.monthly_hours), float(s.monthly_days), 5), **{i.code: 0.0 for i in others}}
    for item in _dependency_order(others):
        if item.calc_method == "FIXO":
            context[item.code] = float(item.amount or 0)
        elif item.calc_method == "PERCENTAGEM":
            context[item.code] = salary * float(item.rate or 0) / 100
        elif item.calc_method == "FORMULA" and item.formula_ast:
            context[item.code] = round2(evaluate(item.formula_ast, context))
    return {"example_salary": salary, "value": round2(evaluate(ast, context))}


# --- the rubricas of an employee ---------------------------------------------------------------------------------

async def employee_items(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID) -> list[dict]:
    await get_employee(db, company_id, employee_id)
    rows = (await db.execute(select(EmployeePayrollItem, PayrollItem).join(PayrollItem, PayrollItem.id == EmployeePayrollItem.item_id)
                             .where(EmployeePayrollItem.employee_id == employee_id).order_by(PayrollItem.position))).all()
    return [{"item_id": i.id, "code": i.code, "name": i.name, "nature": i.nature, "calc_method": i.calc_method,
             "amount": None if e.amount is None else float(e.amount), "rate": None if e.rate is None else float(e.rate),
             "default_amount": None if i.amount is None else float(i.amount), "default_rate": None if i.rate is None else float(i.rate),
             "is_active": i.is_active} for e, i in rows]


async def set_employee_items(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, rows: list[dict]) -> list[dict]:
    """The employee's rubricas, all at once (the list replaces the previous one)."""
    await get_employee(db, company_id, employee_id)
    items = {i.id: i for i in (await db.execute(select(PayrollItem).where(PayrollItem.company_id == company_id))).scalars()}
    current = {e.item_id: e for e in (await db.execute(select(EmployeePayrollItem).where(
        EmployeePayrollItem.employee_id == employee_id))).scalars()}
    seen = set()
    for row in rows:
        try:
            item_id = uuid.UUID(str(row.get("item_id")))
        except ValueError:
            raise PayrollError("Rubrica inválida")
        item = items.get(item_id)
        if item is None:
            raise PayrollError("Rubrica inválida")
        if item_id in seen:
            raise PayrollError(f"A rubrica {item.name} aparece duas vezes")
        seen.add(item_id)
        if item.calc_method == "MENSAL":
            raise PayrollError(f"{item.name} é indicada em cada mês, não na ficha")
        if not item.is_active and item_id not in current:
            raise PayrollError(f"{item.name} está desativada")
        amount = rate = None
        if item.calc_method == "FIXO":
            value = row.get("amount")
            if value in (None, ""):
                if item.amount is None:
                    raise PayrollError(f"{item.name}: indique o valor")
            else:
                amount = round2(_number(value, item.name, 0))
        elif item.calc_method == "PERCENTAGEM" and row.get("rate") not in (None, ""):
            rate = _number(row.get("rate"), item.name + " (%)", 0, 1000)
        link = current.get(item_id)
        if link is None:
            db.add(EmployeePayrollItem(company_id=company_id, employee_id=employee_id, item_id=item_id, amount=amount, rate=rate))
        else:
            link.amount, link.rate = amount, rate
    for item_id, link in current.items():
        if item_id not in seen:
            await db.delete(link)
    await db.commit()
    return await employee_items(db, company_id, employee_id)


# --- the payslip -------------------------------------------------------------------------------------------------

def _builtins(salary: float, hours: float, days: float, seniority: int) -> dict:
    return {"SB": salary, "HORAS_MES": hours, "DIAS_MES": days, "VH": salary / hours if hours else 0.0,
            "VD": salary / days if days else 0.0, "ANTIGUIDADE": float(seniority)}


def _seniority(hired_on: date, day: date) -> int:
    years = day.year - hired_on.year - ((day.month, day.day) < (hired_on.month, hired_on.day))
    return max(0, years)


def compute_payslip(salary: float, settings: dict, brackets: list[dict] | None, items: list[dict], seniority: int) -> dict:
    """The payslip from plain values (no database: the monthly calculation of step 4 calls it too).
    items: [{code, name, nature, calc_method, amount, rate, formula_ast, subject_inss, subject_irt, irt_exempt_limit,
    applies (bool), month_value}] - every active rubrica of the company, the ones that do not apply included (a formula
    may read them: 0)."""
    context = _builtins(salary, settings["monthly_hours"], settings["monthly_days"], seniority)
    context.update({i["code"]: 0.0 for i in items})
    stand_ins = [PayrollItem(code=i["code"], calc_method=i["calc_method"], formula_ast=i.get("formula_ast")) for i in items]
    by_code = {i["code"]: i for i in items}
    lines = []
    for stand_in in _dependency_order(stand_ins):
        i = by_code[stand_in.code]
        if not i["applies"]:
            continue
        method = i["calc_method"]
        if method == "FIXO":
            value = float(i["amount"] or 0)
        elif method == "PERCENTAGEM":
            value = salary * float(i["rate"] or 0) / 100
        elif method == "FORMULA":
            value = evaluate(i["formula_ast"], context)
        else:
            value = float(i.get("month_value") or 0)
        value = round2(max(0.0, value))
        context[i["code"]] = value
        if value:
            lines.append({**{k: i[k] for k in ("code", "name", "nature", "subject_inss", "subject_irt", "irt_exempt_limit")}, "value": value})

    allowances = [line for line in lines if line["nature"] == "ABONO"]
    deductions = [line for line in lines if line["nature"] == "DESCONTO"]
    gross = round2(salary + sum(line["value"] for line in allowances))
    inss_base = round2(max(0.0, salary + sum(line["value"] for line in allowances if line["subject_inss"])
                           - sum(line["value"] for line in deductions if line["subject_inss"])))
    inss_employee = round2(inss_base * settings["inss_employee_rate"] / 100)
    inss_employer = round2(inss_base * settings["inss_employer_rate"] / 100)
    for line in allowances:  # the part of each allowance that is taxed
        taxed = line["value"] if line["subject_irt"] else 0.0
        if line["subject_irt"] and line["irt_exempt_limit"] is not None:
            taxed = max(0.0, line["value"] - float(line["irt_exempt_limit"]))
        line["irt_taxed"] = round2(taxed)
    irt_base = round2(max(0.0, salary + sum(line["irt_taxed"] for line in allowances)
                          - sum(line["value"] for line in deductions if line["subject_irt"])
                          - (inss_employee if settings["inss_deducted_from_irt"] else 0.0)))
    irt = irt_of(irt_base, brackets) if brackets else 0.0
    total_deductions = round2(inss_employee + irt + sum(line["value"] for line in deductions))
    return {
        "base_salary": round2(salary), "allowances": allowances, "deductions": deductions, "gross": gross,
        "inss_base": inss_base, "inss_employee": inss_employee, "inss_employer": inss_employer,
        "irt_base": irt_base, "irt": irt, "total_deductions": total_deductions, "net": round2(gross - total_deductions),
        "employer_cost": round2(gross + inss_employer),
    }


async def simulate_payslip(db: AsyncSession, company_id: uuid.UUID, employee_id: uuid.UUID, month_values: dict | None = None,
                           day: date | None = None) -> dict:
    """The payslip the employee would get today with the current settings (and the month's values given)."""
    employee: Employee = await get_employee(db, company_id, employee_id)
    s = await ensure_payroll_defaults(db, company_id)
    day = day or date.today()
    table = await irt_table_on(db, company_id, day)
    given = {e.item_id: e for e in (await db.execute(select(EmployeePayrollItem).where(
        EmployeePayrollItem.employee_id == employee_id))).scalars()}
    month_values = {str(k).upper(): v for k, v in (month_values or {}).items()}
    items = []
    for i in (await db.execute(select(PayrollItem).where(PayrollItem.company_id == company_id, PayrollItem.is_active.is_(True))
                               .order_by(PayrollItem.position))).scalars():
        link = given.get(i.id)
        if i.calc_method == "MENSAL":
            month_value = round2(_number(month_values.get(i.code) or 0, i.name, 0))
            applies = month_value > 0
        else:
            month_value, applies = None, i.applies_to_all or link is not None
        items.append({"code": i.code, "name": i.name, "nature": i.nature, "calc_method": i.calc_method,
                      "amount": link.amount if link is not None and link.amount is not None else i.amount,
                      "rate": link.rate if link is not None and link.rate is not None else i.rate,
                      "formula_ast": i.formula_ast, "subject_inss": i.subject_inss, "subject_irt": i.subject_irt,
                      "irt_exempt_limit": i.irt_exempt_limit, "applies": applies, "month_value": month_value})
    try:
        slip = compute_payslip(float(employee.base_salary), _settings(s), table.brackets if table else None, items,
                               _seniority(employee.hired_on, day))
    except FormulaError as e:
        raise PayrollError(str(e))
    return {**slip, "employee": employee.full_name, "number": employee.number, "day": day,
            "irt_table": table.name if table else None,
            "warning": None if table else "Nenhuma tabela de IRT em vigor nesta data: o IRT não foi calculado"}
