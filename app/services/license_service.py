"""
Licenças das instalações locais (app/core/license.py).

On the RM SOFT platform: generate_license makes a company's licence file from its current contract, for one server.
On a client's server (LICENSE_REQUIRED=true): import_license keeps the file after checking it; license_contract gives
plan_service the company's terms read FROM THE FILE (plan, limits, options, dates) - the database's contracts are not
used there. Without a valid licence: the same rule as an ended contract, counted from the company's creation (7 days,
then read only), so a fresh installation works while its licence is being issued.
"""
import uuid
from dataclasses import dataclass, field
from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.license import LicenseError, installation_code, normalize_code, read_license, sign_license
from app.core.plan_features import OPTIONS
from app.models.company import Company
from app.models.plan import CompanyLicense

NO_LICENSE = "SEM_LICENCA"


@dataclass
class LicensePlan:
    name: str
    limits: dict
    options: list


@dataclass
class LicenseContract:
    """The company's terms as the licence says - shaped like a CompanyContract for plan_service."""
    plan: LicensePlan
    billing: str
    start_date: date | None
    end_date: date | None
    maintenance_until: date | None
    addons: dict = field(default_factory=dict)
    issued_at: str | None = None
    problem: str | None = None  # why there is no valid licence (None: the licence is valid)


def _day(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


# ------------------------------------------------------------------------------------------------------ the platform

async def generate_license(db: AsyncSession, company_id: uuid.UUID, code: str) -> tuple[str, str]:
    """The licence file of the company's current contract for the server showing this code: (content, file name)."""
    from app.services.plan_service import current_contract
    company = await db.get(Company, company_id)
    contract = await current_contract(db, company_id)
    if company is None or contract is None:
        raise LicenseError("A empresa não tem contrato - guarde primeiro o contrato")
    if contract.deployment_mode != "LOCAL":
        raise LicenseError("O contrato desta empresa é SaaS: a licença é só para a instalação local (mude a instalação no contrato)")
    data = {
        "v": 1, "nif": company.nif, "company": company.short_name or company.name, "installation": normalize_code(code),
        "plan": {"name": contract.plan.name, "limits": contract.plan.limits or {}, "options": list(contract.plan.options or [])},
        "addons": contract.addons or {}, "billing": contract.billing,
        "start_date": contract.start_date.isoformat(),
        "end_date": contract.end_date.isoformat() if contract.end_date else None,
        "maintenance_until": contract.maintenance_until.isoformat() if contract.maintenance_until else None,
        "issued_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "contract_id": str(contract.id),
    }
    name = f"licenca_{company.nif}_{data['installation'].replace('-', '')[:8]}_{date.today().isoformat()}.lic"
    return sign_license(data), name


# ---------------------------------------------------------------------------------------------- the client's server

_checked: dict[str, dict] = {}  # licence text -> its checked content (the signature is checked once per text)


def _checked_content(text: str) -> dict:
    if text not in _checked:
        _checked[text] = read_license(text)
    return _checked[text]


def _matches(data: dict, company: Company) -> str | None:
    """Why this licence is not this company's on this server, None when it is."""
    if data.get("nif") != company.nif:
        return f"Esta licença é da empresa com o NIF {data.get('nif')}, não de {company.short_name or company.name} ({company.nif})"
    if data.get("installation") != installation_code():
        return (f"Esta licença foi emitida para outro servidor (código {data.get('installation')}); o código deste "
                f"servidor é {installation_code()} - peça uma licença para este código à RM SOFT")
    return None


async def import_license(db: AsyncSession, company_id: uuid.UUID, text: str, user_id: uuid.UUID | None) -> dict:
    """Checks the file (signature, company, server) and makes it the company's licence - the previous stays as history."""
    company = await db.get(Company, company_id)
    if company is None:
        raise LicenseError("Empresa não encontrada")
    text = "".join((text or "").split())
    data = read_license(text)
    problem = _matches(data, company)
    if problem:
        raise LicenseError(problem)
    previous = (await db.execute(select(CompanyLicense).where(CompanyLicense.company_id == company_id,
                                                              CompanyLicense.is_current.is_(True)))).scalar_one_or_none()
    if previous is not None:
        previous.is_current = False
        await db.flush()
    db.add(CompanyLicense(company_id=company_id, content=text, imported_by_user_id=user_id))
    await db.commit()
    return await license_view(db, company_id)


async def license_contract(db: AsyncSession, company_id: uuid.UUID) -> LicenseContract:
    """The company's terms from its licence - or, without a valid one, the terms of "no licence" (everything, ended at
    the company's creation: 7 days, then read only)."""
    company = await db.get(Company, company_id)
    row = (await db.execute(select(CompanyLicense.content).where(CompanyLicense.company_id == company_id,
                                                                 CompanyLicense.is_current.is_(True)))).first()
    problem = "Esta instalação ainda não tem licença"
    if row is not None and company is not None:
        try:
            data = _checked_content(row[0])
            problem = _matches(data, company)
        except LicenseError as e:
            problem = str(e)
        if problem is None:
            plan = data["plan"]
            return LicenseContract(plan=LicensePlan(plan["name"], plan.get("limits") or {}, plan.get("options") or []),
                                   billing=data["billing"], start_date=_day(data.get("start_date")),
                                   end_date=_day(data.get("end_date")), maintenance_until=_day(data.get("maintenance_until")),
                                   addons=data.get("addons") or {}, issued_at=data.get("issued_at"))
    created = company.created_at.date() if company is not None and company.created_at else date.today()
    return LicenseContract(plan=LicensePlan("Sem licença", {}, list(OPTIONS)), billing=NO_LICENSE, start_date=created,
                           end_date=created, maintenance_until=None, problem=problem)


async def license_view(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """What the Licença screen shows: this server's code, the licence (or why there is none) and where it is."""
    from app.services.plan_service import contract_status
    terms = await license_contract(db, company_id)
    status = contract_status(terms)
    return {
        "installation_code": installation_code(),
        "valid": terms.problem is None, "problem": terms.problem,
        "plan": terms.plan.name if terms.problem is None else None,
        "limits": terms.plan.limits if terms.problem is None else None,
        "options": terms.plan.options if terms.problem is None else None,
        "addons": terms.addons, "billing": terms.billing if terms.problem is None else None,
        "start_date": terms.start_date if terms.problem is None else None,
        "end_date": terms.end_date if terms.problem is None else None,
        "maintenance_until": terms.maintenance_until, "issued_at": terms.issued_at,
        "status": status["status"], "grace_until": status["grace_until"], "read_only": status["read_only"],
    }
