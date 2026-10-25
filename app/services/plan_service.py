"""
Planos (SUPER_ADMIN) and each company's contract - and what they allow.

What a company may do = its current contract's plan (limits + options) plus the contract's add-ons. A company without
a current contract has no limit at all (an installation not yet given one never blocks).

Enforced here and called from where a limited thing is created or switched back on:
  check_limit(db, company_id, "max_users", adding=1)  - users, modules, shops, tills, warehouses
  has_option(db, company_id, "COPIAS_AUTOMATICAS")      - the options without a permission of their own
and, for the options that own permissions (suppliers, guias, the assistant...), permission_service refuses and hides
them (plan_allows).
"""
import uuid
from datetime import date, timedelta
from decimal import Decimal

import calendar

from sqlalchemy import func, select, true
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.plan_features import (BILLING_TYPES, DEPLOYMENT_MODES, GRACE_DAYS, LIMITS, OPTIONS, TRIAL_DAYS, WARN_DAYS,
                                    option_of_permission)
from app.models.plan import CompanyContract, Plan


class PlanError(Exception):
    """Raised when a plan or a contract is refused (a name taken, an unknown option, dates out of order...)."""


class PlanLimitError(Exception):
    """Raised when the company's plan does not allow it (a 4th user on a plan of 3...) - answered 422 (main.py)."""


# ------------------------------------------------------------------------------------------------------------ the plans

def _clean_limits(limits: dict | None) -> dict:
    clean = {}
    for code, value in (limits or {}).items():
        if code not in LIMITS:
            raise PlanError(f"Limite desconhecido: {code}")
        if value is not None:
            value = int(value)
            if value < 0:
                raise PlanError(f"{LIMITS[code].label}: o número não pode ser negativo")
        clean[code] = value
    return clean


def _clean_options(options: list[str] | None) -> list[str]:
    unknown = [o for o in (options or []) if o not in OPTIONS]
    if unknown:
        raise PlanError(f"Opção desconhecida: {unknown[0]}")
    return [o for o in OPTIONS if o in (options or [])]  # the catalog's order, no duplicate


async def list_plans(db: AsyncSession, active_only: bool = False) -> list[Plan]:
    query = select(Plan).order_by(Plan.sort_order, Plan.name)
    if active_only:
        query = query.where(Plan.is_active.is_(True))
    return list((await db.execute(query)).scalars().all())


async def get_plan_or_raise(db: AsyncSession, plan_id: uuid.UUID) -> Plan:
    plan = await db.get(Plan, plan_id)
    if plan is None:
        raise PlanError("Plano não encontrado")
    return plan


async def save_plan(db: AsyncSession, plan_id: uuid.UUID | None, data: dict) -> Plan:
    """Creates (plan_id None) or edits a plan. A change applies at once to the companies on this plan - their
    contracts point to it (a company keeps what it had only through its own add-ons)."""
    name = (data.get("name") or "").strip()
    if not name:
        raise PlanError("Indique o nome do plano")
    taken = (await db.execute(select(Plan.id).where(func.lower(Plan.name) == name.lower(),
                                                    Plan.id != plan_id if plan_id else true()))).first()
    if taken:
        raise PlanError(f"Já existe um plano «{name}»")
    plan = await get_plan_or_raise(db, plan_id) if plan_id else Plan()
    plan.name = name
    plan.description = (data.get("description") or "").strip() or None
    plan.description_en = (data.get("description_en") or "").strip() or None
    for field in ("price_monthly", "price_quarterly", "price_semiannual", "price_annual", "price_lifetime",
                  "maintenance_percent"):
        value = data.get(field)
        if value is not None and Decimal(str(value)) < 0:
            raise PlanError("Os preços não podem ser negativos")
        setattr(plan, field, value)
    plan.limits = _clean_limits(data.get("limits"))
    plan.options = _clean_options(data.get("options"))
    plan.is_popular = bool(data.get("is_popular"))
    plan.sort_order = int(data.get("sort_order") or 0)
    plan.is_active = bool(data.get("is_active", True))
    if plan_id is None:
        db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


async def plan_usage_counts(db: AsyncSession) -> dict[uuid.UUID, int]:
    """How many companies have each plan now - shown on the plans page."""
    rows = (await db.execute(select(CompanyContract.plan_id, func.count()).where(CompanyContract.is_current.is_(True))
                             .group_by(CompanyContract.plan_id))).all()
    return {plan_id: count for plan_id, count in rows}


# -------------------------------------------------------------------------------------------------------- the contracts

async def current_contract(db: AsyncSession, company_id: uuid.UUID) -> CompanyContract | None:
    return (await db.execute(select(CompanyContract).where(CompanyContract.company_id == company_id,
                                                           CompanyContract.is_current.is_(True)))).scalar_one_or_none()


async def list_contracts(db: AsyncSession, company_id: uuid.UUID) -> list[CompanyContract]:
    return list((await db.execute(select(CompanyContract).where(CompanyContract.company_id == company_id)
                                  .order_by(CompanyContract.created_at.desc()))).scalars().all())


def add_months(day: date, months: int) -> date:
    """The same day, so many months later (31 January + 1 month: 28/29 February)."""
    month = day.month - 1 + months
    year, month = day.year + month // 12, month % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def default_end(billing: str, start: date) -> date | None:
    """When a period paid this way ends: 15 days for the trial, the months for the others, never for the lifetime."""
    if billing == "TESTE":
        return start + timedelta(days=TRIAL_DAYS - 1)
    months = BILLING_TYPES[billing][1]
    return None if months is None else add_months(start, months) - timedelta(days=1)


async def set_contract(db: AsyncSession, company_id: uuid.UUID, data: dict, user_id: uuid.UUID | None = None,
                       commit: bool = True) -> CompanyContract:
    """A new current contract (a renewal, a change of plan...): the previous one stays as history. Refused when the
    company already uses more than the new plan allows - the platform first asks it to reduce."""
    plan = await get_plan_or_raise(db, data["plan_id"])
    billing, mode = data.get("billing") or "ANUAL", data.get("deployment_mode") or "SAAS"
    if billing not in BILLING_TYPES:
        raise PlanError("Escolha o tipo de pagamento")
    if mode not in DEPLOYMENT_MODES:
        raise PlanError("Escolha o modo de instalação")
    if billing == "VITALICIA" and mode != "LOCAL":
        raise PlanError("A licença vitalícia é só para a instalação local (servidor do cliente)")
    start = data.get("start_date") or date.today()
    end = data["end_date"] if "end_date" in data else default_end(billing, start)
    if billing == "VITALICIA":
        end = None
    if end is not None and end < start:
        raise PlanError("A data de fim é anterior à data de início")
    maintenance = data.get("maintenance_until")
    if billing == "VITALICIA" and maintenance is None:
        maintenance = add_months(start, 12) - timedelta(days=1)  # the first year of updates is included
    addons = {k: v for k, v in _clean_limits(data.get("addons")).items() if v}

    contract = CompanyContract(
        company_id=company_id, plan_id=plan.id, deployment_mode=mode, billing=billing, start_date=start, end_date=end,
        maintenance_until=maintenance if billing == "VITALICIA" else None, addons=addons, price=data.get("price"),
        notes=(data.get("notes") or "").strip() or None, created_by_user_id=user_id,
    )
    over = await _over_limits(db, company_id, _effective_limits(plan, addons))
    if over:
        raise PlanError("A empresa já usa mais do que este plano permite: " + "; ".join(over)
                        + ". Reduza primeiro, ou acrescente no contrato.")
    previous = await current_contract(db, company_id)
    if previous is not None:
        previous.is_current = False
        await db.flush()  # one current contract per company (partial unique index)
    db.add(contract)
    await _switch_off_lost_options(db, company_id, plan.options)
    if commit:
        await db.commit()
        await db.refresh(contract)
    return contract


async def _switch_off_lost_options(db: AsyncSession, company_id: uuid.UUID, options: list[str]) -> None:
    """A plan without the assistant (or its channels), or without automatic copies: those switches go off."""
    from app.models.company_ai_settings import CompanyAiSettings
    from app.models.company_backup import CompanyBackupSettings
    ai = (await db.execute(select(CompanyAiSettings).where(CompanyAiSettings.company_id == company_id))).scalar_one_or_none()
    if ai is not None:
        if "ASSISTENTE_IA" not in options:
            ai.ai_enabled = False
        if "ASSISTENTE_IA" not in options or "IA_CANAIS" not in options:
            ai.whatsapp_enabled = ai.telegram_enabled = False
    if "COPIAS_AUTOMATICAS" not in options:
        backup = (await db.execute(select(CompanyBackupSettings)
                                   .where(CompanyBackupSettings.company_id == company_id))).scalar_one_or_none()
        if backup is not None and backup.mode == "AUTOMATICA":
            backup.mode, backup.next_run_at = "MANUAL", None


# ------------------------------------------------------------------------------------------------------ what it allows

def _effective_limits(plan: Plan, addons: dict) -> dict:
    """The plan's limits plus the add-ons; None = unlimited (a limit the plan does not set is unlimited)."""
    result = {}
    for code in LIMITS:
        base = (plan.limits or {}).get(code)
        result[code] = None if base is None else base + int((addons or {}).get(code) or 0)
    return result


def _license_mode() -> bool:
    from app.core.config import get_settings
    return get_settings().LICENSE_REQUIRED


async def current_terms(db: AsyncSession, company_id: uuid.UUID):
    """What the company's limits, options and dates are read from: its current contract - or, on a client's server
    (LICENSE_REQUIRED), its licence file (license_service), the database's contracts being ignored there."""
    if _license_mode():
        from app.services.license_service import license_contract
        return await license_contract(db, company_id)
    return await current_contract(db, company_id)


async def entitlements(db: AsyncSession, company_id: uuid.UUID) -> dict | None:
    """{"plan": name, "limits": {...}, "options": [...]} - None without a current contract (nothing limited)."""
    contract = await current_terms(db, company_id)
    if contract is None:
        return None
    return {"plan": contract.plan.name, "limits": _effective_limits(contract.plan, contract.addons),
            "options": list(contract.plan.options or [])}


async def usage(db: AsyncSession, company_id: uuid.UUID) -> dict[str, int]:
    """What the company uses now, for each limit."""
    from app.models.activity import Activity
    from app.models.company_module import CompanyModule
    from app.models.establishment import Establishment
    from app.models.point_of_sale import PointOfSale
    from app.models.user import User
    from app.models.warehouse import Warehouse

    async def count(query) -> int:
        return int((await db.execute(query)).scalar_one())

    activity_warehouses = select(Activity.warehouse_id).where(Activity.company_id == company_id,
                                                              Activity.warehouse_id.is_not(None))
    return {
        "max_users": await count(select(func.count()).select_from(User).where(User.company_id == company_id,
                                                                              User.is_active.is_(True))),
        "max_modules": await count(select(func.count()).select_from(CompanyModule).where(
            CompanyModule.company_id == company_id, CompanyModule.is_enabled.is_(True))),
        "max_establishments": await count(select(func.count()).select_from(Establishment).where(
            Establishment.company_id == company_id, Establishment.is_active.is_(True))),
        "max_pos": await count(select(func.count()).select_from(PointOfSale).where(
            PointOfSale.company_id == company_id, PointOfSale.is_active.is_(True))),
        # the activities' own point-of-sale warehouses come with the activity: only the company's stores count
        "max_warehouses": await count(select(func.count()).select_from(Warehouse).where(
            Warehouse.company_id == company_id, Warehouse.is_active.is_(True), Warehouse.id.not_in(activity_warehouses))),
    }


async def _over_limits(db: AsyncSession, company_id: uuid.UUID, limits: dict) -> list[str]:
    used = await usage(db, company_id)
    over = []
    for code, limit in limits.items():
        if limit is not None and used[code] > limit:
            over.append(f"{LIMITS[code].label.lower()}: {used[code]} para {limit}")
    return over


def _limit_message(plan: str, code: str, limit: int) -> str:
    lim = LIMITS[code]
    noun = lim.noun_one if limit == 1 else lim.noun_many
    return (f"O plano {plan} permite {limit} {noun}. Para mais, contacte a RM SOFT "
            f"(mudança de plano ou acréscimo no contrato).")


async def check_limit(db: AsyncSession, company_id: uuid.UUID, code: str, adding: int = 1,
                      total: int | None = None) -> None:
    """Refuses when this would take the company over its plan: `adding` more than it uses now, or exactly `total`
    (the modules: the new set replaces the old one)."""
    rights = await entitlements(db, company_id)
    if rights is None:
        return
    limit = rights["limits"].get(code)
    if limit is None:
        return
    wanted = total if total is not None else (await usage(db, company_id))[code] + adding
    if wanted > limit:
        raise PlanLimitError(_limit_message(rights["plan"], code, limit))


async def check_plan_limit(db: AsyncSession, plan_id: uuid.UUID | None, code: str, total: int,
                           addons: dict | None = None) -> None:
    """Before the company exists (its creation): the chosen plan allows this many?"""
    if plan_id is None:
        return
    plan = await get_plan_or_raise(db, plan_id)
    limit = _effective_limits(plan, addons or {}).get(code)
    if limit is not None and total > limit:
        raise PlanLimitError(_limit_message(plan.name, code, limit))


async def has_option(db: AsyncSession, company_id: uuid.UUID, option: str) -> bool:
    rights = await entitlements(db, company_id)
    return rights is None or option in rights["options"]


async def require_option(db: AsyncSession, company_id: uuid.UUID, option: str) -> None:
    rights = await entitlements(db, company_id)
    if rights is not None and option not in rights["options"]:
        raise PlanLimitError(f"«{OPTIONS[option].label}» não está incluído no plano {rights['plan']}. "
                             f"Para o ter, contacte a RM SOFT (mudança de plano).")


async def company_options_or_none(db: AsyncSession, company_id: uuid.UUID) -> set[str] | None:
    """The plan's options - None without a contract (everything allowed). One small query."""
    if _license_mode():
        return set((await current_terms(db, company_id)).plan.options or [])
    row = (await db.execute(select(Plan.options).join(CompanyContract, CompanyContract.plan_id == Plan.id)
                            .where(CompanyContract.company_id == company_id, CompanyContract.is_current.is_(True)))).first()
    return None if row is None else set(row[0] or [])


def plan_allows_code(options: set[str] | None, code: str) -> bool:
    if options is None:
        return True
    option = option_of_permission(code)
    return option is None or option in options


async def plan_allows(db: AsyncSession, company_id: uuid.UUID, code: str) -> bool:
    """False when this permission belongs to an option the company's plan does not have. Most permissions belong to
    none: no query for them."""
    if option_of_permission(code) is None:
        return True
    return plan_allows_code(await company_options_or_none(db, company_id), code)


# ------------------------------------------------------------------------------------------------------------ the end

def contract_status(contract: CompanyContract | None, today: date | None = None) -> dict:
    """Where the company is in its contract:
      ATIVO       - nothing to say (no contract, no end, the lifetime licence, or more than 15 days left)
      A_EXPIRAR   - 15 days or less before the end: the gestor is told
      TOLERANCIA  - ended less than 7 days ago: everything still works, the gestor is told it stops soon
      BLOQUEADO   - ended more than 7 days ago: read only (see everything, export the SAF-T, download the copies;
                    no sale, no document, no change) until a new contract
    The lifetime licence never ends; its maintenance can (maintenance_over: no more updates - nothing blocked)."""
    today = today or date.today()
    view = {"status": "ATIVO", "plan": None, "billing": None, "end_date": None, "days_left": None,
            "grace_until": None, "read_only": False, "maintenance_until": None, "maintenance_over": False,
            "license_problem": None}
    if contract is None:
        return view
    view.update(plan=contract.plan.name, billing=contract.billing, end_date=contract.end_date,
                maintenance_until=contract.maintenance_until,
                license_problem=getattr(contract, "problem", None))  # a client's server without a valid licence
    if contract.billing == "VITALICIA":
        view["maintenance_over"] = contract.maintenance_until is not None and contract.maintenance_until < today
        return view
    if contract.end_date is None:
        return view
    grace_until = contract.end_date + timedelta(days=GRACE_DAYS)
    view["grace_until"] = grace_until
    if today <= contract.end_date:
        days = (contract.end_date - today).days
        view["days_left"] = days
        if days < WARN_DAYS:
            view["status"] = "A_EXPIRAR"
    elif today <= grace_until:
        view.update(status="TOLERANCIA", days_left=(grace_until - today).days)
    else:
        view.update(status="BLOQUEADO", read_only=True, days_left=0)
    return view


async def subscription(db: AsyncSession, company_id: uuid.UUID) -> dict:
    return contract_status(await current_terms(db, company_id))


async def statuses_by_company(db: AsyncSession) -> dict[uuid.UUID, dict]:
    """Every company's contract status in one query - the platform's company list."""
    if _license_mode():
        from app.models.company import Company
        ids = (await db.execute(select(Company.id))).scalars().all()
        return {company_id: await subscription(db, company_id) for company_id in ids}
    rows = (await db.execute(select(CompanyContract).where(CompanyContract.is_current.is_(True)))).scalars().all()
    return {row.company_id: contract_status(row) for row in rows}


READ_ONLY_MESSAGE = ("O contrato desta empresa terminou: o sistema está só de leitura (consultar, exportar o SAF-T e "
                     "descarregar as cópias continua possível). Para voltar a vender, contacte a RM SOFT.")
LICENSE_READ_ONLY_MESSAGE = ("Esta instalação não tem licença válida: o sistema está só de leitura (consultar, exportar o "
                             "SAF-T e descarregar as cópias continua possível). Importe a licença em Definições da "
                             "Empresa → Licença, ou contacte a RM SOFT.")


def read_only_message() -> str:
    return LICENSE_READ_ONLY_MESSAGE if _license_mode() else READ_ONLY_MESSAGE

# what a company in read only may still do (POST...): sign in, change its password, end a support access, a copy now
# and import its new licence (a client's server)
_ALLOWED_WHEN_READ_ONLY = ("/api/v1/auth/login", "/api/v1/auth/refresh", "/api/v1/auth/me/password",
                           "/api/v1/auth/support/", "/api/v1/company/me/backups", "/api/v1/company/me/license")


def allowed_when_read_only(method: str, path: str) -> bool:
    return method in ("GET", "HEAD", "OPTIONS") or any(path.startswith(p) for p in _ALLOWED_WHEN_READ_ONLY)


async def is_read_only(db: AsyncSession, company_id: uuid.UUID) -> bool:
    """One small query: the current contract's dates only."""
    if _license_mode():
        return (await subscription(db, company_id))["read_only"]
    row = (await db.execute(select(CompanyContract.billing, CompanyContract.end_date)
                            .where(CompanyContract.company_id == company_id, CompanyContract.is_current.is_(True)))).first()
    if row is None or row.billing == "VITALICIA" or row.end_date is None:
        return False
    return date.today() > row.end_date + timedelta(days=GRACE_DAYS)
