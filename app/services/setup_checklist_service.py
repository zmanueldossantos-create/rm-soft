"""
Configuração inicial: what a new company still has to set up before working normally. Each item is read from the real
data (nothing is ticked by hand), so it ticks itself as soon as the gestor does the step - and unticks if he undoes it.

Required items count in the progress; recommended ones are shown but never block. Items owned by the platform (the
fiscal regime, the commercial registration number) are set by RM SOFT: the gestor sees them without a "Ir" link.
"""
import uuid
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.activity import Activity
from app.models.company import Company
from app.models.company_bank_account import CompanyBankAccount
from app.models.company_email_settings import CompanyEmailSettings
from app.models.document_series import DocumentSeries
from app.models.establishment import Establishment
from app.models.fiscal_period import FiscalPeriod
from app.models.fiscal_year import FiscalYear
from app.models.product import Product
from app.models.service import Service
from app.models.user import User, UserRole
from app.models.user_cash_point_access import UserCashPointAccess

PLATFORM = "RM SOFT"  # owner of the items the gestor cannot change himself


async def _count(db: AsyncSession, model, *conditions) -> int:
    return (await db.execute(select(func.count()).select_from(model).where(*conditions))).scalar_one()


def _item(key: str, label: str, done: bool, detail: str, link: str | None, required: bool = True,
          owner: str | None = None) -> dict:
    return {"key": key, "label": label, "done": done, "detail": detail, "link": link, "required": required,
            "owner": owner}


async def get_setup_checklist(db: AsyncSession, company_id: uuid.UUID) -> dict:
    """The company's set-up items, in the order they are best done, with the progress of the required ones."""
    company = await db.get(Company, company_id)
    year = date.today().year
    items: list[dict] = []

    # 1. The data printed on every document
    missing = [label for label, value in (("morada", company.address), ("cidade", company.city)) if not (value or "").strip()]
    items.append(_item("dados", "Dados da empresa", not missing,
                       "Falta: " + ", ".join(missing) if missing else "Morada e cidade preenchidas",
                       "/company-settings?tab=dados"))
    items.append(_item("registo", "N.º de registo comercial", bool((company.commercial_registration_number or "").strip()),
                       "Exigido no ficheiro SAF-T" if not company.commercial_registration_number
                       else company.commercial_registration_number, None, owner=PLATFORM))
    items.append(_item("regime", "Regime fiscal (IVA)", company.fiscal_regime_id is not None,
                       "Define as taxas de IVA que a empresa pode usar" if company.fiscal_regime_id is None
                       else "Definido", None, owner=PLATFORM))

    # 2. Where the company sells
    activities = await _count(db, Activity, Activity.company_id == company_id, Activity.is_active.is_(True))
    items.append(_item("atividade", "Atividade criada", activities > 0,
                       f"{activities} atividade(s) ativa(s)" if activities else "Crie pelo menos uma (ex.: Loja, Bar, Hotel)",
                       "/company-settings?tab=atividades"))
    electronic = company.issuance_mode == "ELETRONICA"
    if electronic:
        establishments = await _count(db, Establishment, Establishment.company_id == company_id,
                                      Establishment.is_active.is_(True))
        items.append(_item("estabelecimento", "Estabelecimento", establishments > 0,
                           "Obrigatório na faturação eletrónica (ex.: SEDE)" if not establishments
                           else f"{establishments} estabelecimento(s)", "/company-settings?tab=estabelecimentos"))

    # 3. Numbering and periods: no document without them
    if company.uses_invoicing:
        if not electronic and company.auto_series_year:
            items.append(_item("series", f"Séries de documentos {year}", True,
                               "Criadas automaticamente na primeira emissão", "/company-settings?tab=series"))
        else:
            series = await _count(db, DocumentSeries, DocumentSeries.company_id == company_id, DocumentSeries.year == year,
                                  DocumentSeries.issuance_mode == company.issuance_mode,
                                  DocumentSeries.is_active.is_(True))
            items.append(_item("series", f"Séries de documentos {year}", series > 0,
                               f"{series} série(s) ativa(s)" if series else "Crie as séries do ano antes de emitir",
                               "/company-settings?tab=series"))
    open_period = (await db.execute(
        select(FiscalPeriod.month, FiscalYear.year).join(FiscalYear, FiscalYear.id == FiscalPeriod.fiscal_year_id).where(
            FiscalPeriod.company_id == company_id, FiscalPeriod.status == "ABERTO", FiscalYear.status == "ABERTO",
        ))).first()
    items.append(_item("periodo", "Exercício e período abertos", open_period is not None,
                       f"Período aberto: {open_period[0]:02d}/{open_period[1]}" if open_period
                       else "Abra o exercício e o período do mês", "/fiscal-periods"))

    # 4. What the company sells
    products = await _count(db, Product, Product.company_id == company_id, Product.is_active.is_(True),
                            Product.is_raw_material.is_(False))
    services = await _count(db, Service, Service.company_id == company_id, Service.is_active.is_(True))
    items.append(_item("catalogo", "Produtos ou serviços", products + services > 0,
                       f"{products} produto(s), {services} serviço(s)" if products + services
                       else "Registe o que a empresa vende", "/products"))

    # 5. Recommended: the team, the tills, how customers pay and receive documents
    team = await _count(db, User, User.company_id == company_id, User.is_active.is_(True), User.role != UserRole.GESTOR)
    items.append(_item("equipa", "Utilizadores da equipa", team > 0,
                       f"{team} utilizador(es) além do gestor" if team else "Crie as contas de quem trabalha consigo",
                       "/users", required=False))
    tills = await _count(db, UserCashPointAccess, UserCashPointAccess.company_id == company_id)
    items.append(_item("caixas", "Utilizadores associados às caixas", tills > 0,
                       f"{tills} associação(ões)" if tills else "Sem associação, só o gestor pode vender na caixa",
                       "/company-settings?tab=atividades", required=False))
    banks = await _count(db, CompanyBankAccount, CompanyBankAccount.company_id == company_id,
                         CompanyBankAccount.is_active.is_(True))
    items.append(_item("bancarias", "Coordenadas bancárias", banks > 0,
                       f"{banks} conta(s) nos documentos" if banks else "O IBAN aparece nas faturas",
                       "/company-settings?tab=bancarias", required=False))
    email = (await db.execute(select(CompanyEmailSettings.from_email).where(
        CompanyEmailSettings.company_id == company_id, CompanyEmailSettings.is_active.is_(True)))).scalar_one_or_none()
    items.append(_item("email", "Email de envio", email is not None,
                       email if email else "Para enviar as faturas aos clientes por email",
                       "/company-settings?tab=email", required=False))
    items.append(_item("logotipo", "Logótipo", bool(company.logo_path),
                       "Aparece nos documentos" if company.logo_path else "Opcional - aparece nos documentos",
                       "/company-settings?tab=dados", required=False))

    required = [i for i in items if i["required"]]
    done = sum(1 for i in required if i["done"])
    return {"items": items, "required_done": done, "required_total": len(required),
            "complete": done == len(required), "all_done": all(i["done"] for i in items)}
