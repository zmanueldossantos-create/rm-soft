"""
Business logic for company (tenant) management.
Reserved for SUPER_ADMIN use - platform-level administration only.
See specification v7, section 2.4 and Decision on SUPER_ADMIN scope.
Extended (Video 1) with the 3-tab fields observed in the reference
legalized software: dados da empresa, informacoes fiscais, coordenadas
bancarias (see CompanyBankAccount).
"""
from datetime import date
from app.models.company_fiscal_regime import CompanyFiscalRegime
import uuid

from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.permission_service import grant_default_role_permissions
from app.services.sector_service import ensure_modules_grantable
from app.models.role_permission import RolePermission
from app.models.company_permission_seed import CompanyPermissionSeed
from app.models.company import Company, LegalPersonType, InvoiceIssuanceMode
from app.models.company_bank_account import CompanyBankAccount
from app.models.vat import VAT
from app.models.payment_method_catalog import PaymentMethodCatalog
from app.models.company_payment_method_preference import CompanyPaymentMethodPreference
from app.models.warehouse import Warehouse
from app.models.user import User, UserRole
from app.models.fiscal_regime import FiscalRegime
from app.models.company_module import CompanyModule
from app.core.security import hash_password



class CompanyAlreadyExistsError(Exception):
    """Raised when a company field (name, NIF, email or phone) conflicts with an existing one."""
    pass


class FiscalRegimeNotFoundError(Exception):
    pass


class CompanyNotFoundError(Exception):
    """Raised when a company id does not match any existing company."""
    pass


class InvalidCurrencySelectionError(Exception):
    """Raised when the primary and secondary currency are the same."""
    pass


class BankAccountNotFoundError(Exception):
    pass


def _duplicate_field_message(error: IntegrityError) -> str:
    """Fallback: inspects the underlying Postgres error if a race condition slips past the pre-checks."""
    detail = str(getattr(error, "orig", error))
    if "ix_companies_name" in detail:
        return "Ja existe uma empresa registada com este nome"
    if "ix_companies_nif" in detail:
        return "Ja existe uma empresa registada com este NIF"
    if "ix_companies_email" in detail:
        return "Ja existe uma empresa registada com este email"
    if "ix_companies_phone_number" in detail:
        return "Ja existe uma empresa registada com este numero de telefone"
    return "Ja existe uma empresa registada com estes dados"


async def _legal_rates_for(db: AsyncSession, regime) -> list:
    """
    The legal VAT rates a company receives (catalog legal_vat_rates, SUPER_ADMIN): every active one whose category its
    regime allows (allows_nor for NOR, allows_red for RED...); all of them when the company has no regime.
    """
    from app.models.legal_vat_rate import LegalVatRate
    rates = (await db.execute(
        select(LegalVatRate).where(LegalVatRate.is_active.is_(True)).order_by(LegalVatRate.rate)
    )).scalars().all()
    if regime is None:
        return list(rates)
    return [r for r in rates if getattr(regime, "allows_" + r.tax_category.lower(), False)]


async def _check_field_available(
    db: AsyncSession,
    field,
    value: str,
    message: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """Raises CompanyAlreadyExistsError if another company already uses this value."""
    query = select(Company).where(field == value)
    if exclude_id is not None:
        query = query.where(Company.id != exclude_id)
    result = await db.execute(query)
    if result.scalar_one_or_none() is not None:
        raise CompanyAlreadyExistsError(message)


async def _check_all_fields_available(
    db: AsyncSession,
    name: str,
    nif: str,
    email: str,
    phone_number: str,
    exclude_id: uuid.UUID | None = None,
) -> None:
    """
    Checks uniqueness in the same top-to-bottom order as the form fields
    (name, NIF, email, phone), so the first conflicting field is always
    the one reported - rather than whichever constraint Postgres happens
    to hit first internally.
    """
    name_query = select(Company).where(func.lower(Company.name) == name.lower())
    if exclude_id is not None:
        name_query = name_query.where(Company.id != exclude_id)
    name_result = await db.execute(name_query)
    if name_result.scalar_one_or_none() is not None:
        raise CompanyAlreadyExistsError("Ja existe uma empresa registada com este nome")

    await _check_field_available(db, Company.nif, nif, "Ja existe uma empresa registada com este NIF", exclude_id)
    await _check_field_available(db, Company.email, email, "Ja existe uma empresa registada com este email", exclude_id)
    await _check_field_available(db, Company.phone_number, phone_number, "Ja existe uma empresa registada com este numero de telefone", exclude_id)


def _validate_currencies(primary_currency_id: uuid.UUID | None, secondary_currency_id: uuid.UUID | None) -> None:
    """A currency already picked as primary can't also be picked as secondary (Video 1)."""
    if primary_currency_id is not None and secondary_currency_id is not None and primary_currency_id == secondary_currency_id:
        raise InvalidCurrencySelectionError("A devise secundaria nao pode ser igual a devise principal")


async def create_company(
    db: AsyncSession,
    name: str,
    nif: str,
    email: str,
    phone_number: str,
    gestor_full_name: str,
    gestor_phone_number: str,
    gestor_password: str,
    address: str | None = None,
    commercial_registration_number: str | None = None,
    fiscal_regime_id: uuid.UUID | None = None,
    module_ids: list[uuid.UUID] | None = None,
    short_name: str | None = None,
    legal_person_type: str = "JURIDICA",
    phone_number_2: str | None = None,
    website: str | None = None,
    city: str | None = None,
    province_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None,
    primary_currency_id: uuid.UUID | None = None,
    secondary_currency_id: uuid.UUID | None = None,
    uses_invoicing: bool = True,
    auto_series_year: bool = True,
    allows_future_sale_date: bool = False,
    suggests_last_document_date: bool = False,
    issuance_mode: str = "MANUAL",
    electronic_signature_key: str | None = None,
    bank_accounts: list[dict] | None = None,
) -> Company:
    """
    Creates a new client company, seeds its VAT rates (limited to what the
    chosen fiscal regime allows - see FiscalRegime) and default warehouse,
    grants access to the chosen Modules (Hotel/Padaria/Bar/Restaurante -
    see Module/CompanyModule), creates the company's single GESTOR
    account, and optionally its bank accounts - all in one transaction.
    Only callable by SUPER_ADMIN.
    """
    await _check_all_fields_available(db, name, nif, email, phone_number)
    _validate_currencies(primary_currency_id, secondary_currency_id)
    await ensure_modules_grantable(db, module_ids or [])

    company = Company(
        name=name,
        nif=nif,
        email=email,
        phone_number=phone_number,
        address=address,
        commercial_registration_number=commercial_registration_number,
        fiscal_regime_id=fiscal_regime_id,
        short_name=short_name,
        legal_person_type=LegalPersonType(legal_person_type),
        phone_number_2=phone_number_2,
        website=website,
        city=city,
        province_id=province_id,
        municipality_id=municipality_id,
        primary_currency_id=primary_currency_id,
        secondary_currency_id=secondary_currency_id,
        uses_invoicing=uses_invoicing,
        auto_series_year=auto_series_year if uses_invoicing else False,
        allows_future_sale_date=allows_future_sale_date if uses_invoicing else False,
        suggests_last_document_date=suggests_last_document_date if uses_invoicing else False,
        issuance_mode=InvoiceIssuanceMode(issuance_mode),
        electronic_signature_key=electronic_signature_key if issuance_mode == "ELETRONICA" else None,
    )
    db.add(company)

    try:
        await db.flush()  # get company.id before creating dependent rows
    except IntegrityError as e:
        await db.rollback()
        raise CompanyAlreadyExistsError(_duplicate_field_message(e))

    # Seed VAT rates - only those the fiscal regime allows, if one was chosen.
    # The legal rates (catalog legal_vat_rates) the regime allows - all of them without a regime.
    regime = None
    if fiscal_regime_id is not None:
        regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == fiscal_regime_id))).scalar_one_or_none()
    if regime is not None:
        db.add(CompanyFiscalRegime(company_id=company.id, fiscal_regime_id=regime.id, valid_from=date.today()))
    for legal in await _legal_rates_for(db, regime):
        db.add(VAT(company_id=company.id, name=legal.name, rate=legal.rate, tax_category=legal.tax_category))

    # Default warehouse - Phase 1 keeps a single warehouse per company (section 5.2/2.8).
    db.add(Warehouse(company_id=company.id, name="Armazem Principal"))

    # Numerario is enabled at the Caixa by default - a company with NO payment method available
    # can never complete a single sale, since Payment.payment_method_id is required (nullable=False).
    # Every other method still defaults to unavailable, per CompanyPaymentMethodPreference's own
    # design (absence of a row = False) - the GESTOR enables the rest as needed.
    numerario_result = await db.execute(select(PaymentMethodCatalog).where(PaymentMethodCatalog.code == "NU"))
    numerario = numerario_result.scalar_one_or_none()
    if numerario is not None:
        db.add(CompanyPaymentMethodPreference(company_id=company.id, payment_method_id=numerario.id, available_at_pos=True))


    # Grant the chosen Modules (Hotel/Padaria/Bar/Restaurante) - GESTOR will
    # later configure the concrete Activity for each one (see activity_service).
    for module_id in (module_ids or []):
        db.add(CompanyModule(company_id=company.id, module_id=module_id, is_enabled=True))

    # Bank accounts (onglet 3) - optional; every row given must be complete
    # (enforced by the request schema, not here).
    for account in (bank_accounts or []):
        db.add(CompanyBankAccount(
            company_id=company.id, bank_id=account["bank_id"],
            account_number=account["account_number"], iban=account["iban"],
            currency_id=account["currency_id"],
        ))

    # The company's single GESTOR account - created here by SUPER_ADMIN,
    # never self-created (section 2.4 decision).
    db.add(User(
        company_id=company.id,
        full_name=gestor_full_name,
        phone_number=gestor_phone_number,
        password_hash=hash_password(gestor_password),
        role=UserRole.GESTOR,
    ))

    await grant_default_role_permissions(db, company.id)
    await db.commit()
    await db.refresh(company)
    return company


async def get_company_gestor(db: AsyncSession, company_id: uuid.UUID) -> User | None:
    """Returns the company's single GESTOR user (or None if somehow missing)."""
    result = await db.execute(
        select(User).where(User.company_id == company_id, User.role == UserRole.GESTOR)
    )
    return result.scalar_one_or_none()


async def get_company_or_raise(db: AsyncSession, company_id: uuid.UUID) -> Company:
    result = await db.execute(select(Company).where(Company.id == company_id))
    company = result.scalar_one_or_none()
    if company is None:
        raise CompanyNotFoundError("Empresa nao encontrada")
    return company


async def update_company(
    db: AsyncSession,
    company_id: uuid.UUID,
    name: str,
    nif: str,
    email: str,
    phone_number: str,
    address: str | None = None,
    commercial_registration_number: str | None = None,
    short_name: str | None = None,
    legal_person_type: str = "JURIDICA",
    phone_number_2: str | None = None,
    website: str | None = None,
    city: str | None = None,
    province_id: uuid.UUID | None = None,
    municipality_id: uuid.UUID | None = None,
    primary_currency_id: uuid.UUID | None = None,
    secondary_currency_id: uuid.UUID | None = None,
    uses_invoicing: bool = True,
    auto_series_year: bool = True,
    allows_future_sale_date: bool = False,
    suggests_last_document_date: bool = False,
    issuance_mode: str = "MANUAL",
    electronic_signature_key: str | None = None,
    fiscal_regime_id: uuid.UUID | None = None,
) -> Company:
    """
    Updates a company's editable fields, including NIF, email and phone (all unique).
    fiscal_regime_id CAN be changed here (SUPER_ADMIN only, see routes). When it actually changes,
    the company's existing VAT rates (matched by category against the legal rates catalog, legal_vat_rates) are resynced:
    a rate the new regime does not allow is deactivated, one it allows is (re)activated, created
    if missing. Existing invoice lines keep their own vat_rate_snapshot - never affected by this.
    """
    company = await get_company_or_raise(db, company_id)

    if fiscal_regime_id is not None:
        regime_result = await db.execute(select(FiscalRegime).where(FiscalRegime.id == fiscal_regime_id))
        if regime_result.scalar_one_or_none() is None:
            raise FiscalRegimeNotFoundError("Regime fiscal nao encontrado")

    await _check_all_fields_available(db, name, nif, email, phone_number, exclude_id=company_id)
    _validate_currencies(primary_currency_id, secondary_currency_id)

    company.name = name
    company.nif = nif
    company.email = email
    company.phone_number = phone_number
    company.address = address
    company.commercial_registration_number = commercial_registration_number
    company.short_name = short_name
    company.legal_person_type = LegalPersonType(legal_person_type)
    company.phone_number_2 = phone_number_2
    company.website = website
    company.city = city
    company.province_id = province_id
    company.municipality_id = municipality_id
    company.primary_currency_id = primary_currency_id
    company.secondary_currency_id = secondary_currency_id
    company.uses_invoicing = uses_invoicing
    company.auto_series_year = auto_series_year if uses_invoicing else False
    company.allows_future_sale_date = allows_future_sale_date if uses_invoicing else False
    company.suggests_last_document_date = suggests_last_document_date if uses_invoicing else False
    company.issuance_mode = InvoiceIssuanceMode(issuance_mode)
    company.electronic_signature_key = electronic_signature_key if issuance_mode == "ELETRONICA" else None
    if fiscal_regime_id is not None and fiscal_regime_id != company.fiscal_regime_id:
        company.fiscal_regime_id = fiscal_regime_id
        # The new regime takes effect at once, and stays in the company's regime history.
        db.add(CompanyFiscalRegime(company_id=company_id, fiscal_regime_id=fiscal_regime_id, valid_from=date.today()))
        regime = (await db.execute(select(FiscalRegime).where(FiscalRegime.id == fiscal_regime_id))).scalar_one()
        await sync_company_rates(db, company_id, regime)
    elif fiscal_regime_id is not None:
        company.fiscal_regime_id = fiscal_regime_id

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise CompanyAlreadyExistsError(_duplicate_field_message(e))

    await db.refresh(company)
    return company


async def delete_company(db: AsyncSession, company_id: uuid.UUID) -> None:
    """
    Permanently deletes a company and its dependent data (VAT rates, users, bank accounts).
    Destructive action - the frontend must confirm with the SUPER_ADMIN before calling this.
    """
    company = await get_company_or_raise(db, company_id)

    await db.execute(RolePermission.__table__.delete().where(RolePermission.company_id == company_id))
    await db.execute(CompanyPermissionSeed.__table__.delete().where(CompanyPermissionSeed.company_id == company_id))
    await db.execute(CompanyBankAccount.__table__.delete().where(CompanyBankAccount.company_id == company_id))
    await db.execute(VAT.__table__.delete().where(VAT.company_id == company_id))
    await db.execute(User.__table__.delete().where(User.company_id == company_id))
    await db.delete(company)
    await db.commit()


async def toggle_company_status(db: AsyncSession, company_id: uuid.UUID) -> Company:
    """Toggles a company's is_active flag (activate/deactivate)."""
    company = await get_company_or_raise(db, company_id)
    company.is_active = not company.is_active
    await db.commit()
    await db.refresh(company)
    return company


# ---------- Bank accounts ----------

async def list_bank_accounts(db: AsyncSession, company_id: uuid.UUID) -> list[CompanyBankAccount]:
    result = await db.execute(select(CompanyBankAccount).where(CompanyBankAccount.company_id == company_id))
    return list(result.scalars().all())


async def add_bank_account(
    db: AsyncSession, company_id: uuid.UUID, bank_id: uuid.UUID, account_number: str, iban: str, currency_id: uuid.UUID,
) -> CompanyBankAccount:
    await get_company_or_raise(db, company_id)  # ensures the company exists
    account = CompanyBankAccount(company_id=company_id, bank_id=bank_id, account_number=account_number, iban=iban, currency_id=currency_id)
    db.add(account)
    await db.commit()
    await db.refresh(account)
    return account


async def update_bank_account(
    db: AsyncSession, account_id: uuid.UUID, bank_id: uuid.UUID, account_number: str, iban: str, currency_id: uuid.UUID,
) -> CompanyBankAccount:
    result = await db.execute(select(CompanyBankAccount).where(CompanyBankAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise BankAccountNotFoundError("Conta bancaria nao encontrada")
    account.bank_id = bank_id
    account.account_number = account_number
    account.iban = iban
    account.currency_id = currency_id
    await db.commit()
    await db.refresh(account)
    return account


async def toggle_bank_account(db: AsyncSession, account_id: uuid.UUID) -> CompanyBankAccount:
    result = await db.execute(select(CompanyBankAccount).where(CompanyBankAccount.id == account_id))
    account = result.scalar_one_or_none()
    if account is None:
        raise BankAccountNotFoundError("Conta bancaria nao encontrada")
    account.is_active = not account.is_active
    await db.commit()
    await db.refresh(account)
    return account


async def sync_company_rates(db: AsyncSession, company_id: uuid.UUID, regime) -> None:
    """
    THE resync of a company's VAT rates with the legal rates its regime allows (catalog legal_vat_rates), matched by
    category - never by name: a category the regime does not allow is deactivated, one it allows is (re)activated,
    or created from its legal rate when the company has none. The regime decides which categories are active - the
    company rates are SUPER_ADMIN managed. Invoice lines keep their own snapshot. No commit.
    """
    existing = (await db.execute(select(VAT).where(VAT.company_id == company_id))).scalars().all()
    allowed_legal = {r.tax_category: r for r in await _legal_rates_for(db, regime)}
    held = set()
    for v in existing:
        v.is_active = v.tax_category in allowed_legal
        held.add(v.tax_category)
    for category, legal in allowed_legal.items():
        if category not in held:
            db.add(VAT(company_id=company_id, name=legal.name, rate=legal.rate, tax_category=category, is_active=True))


async def propagate_regime_rates(db: AsyncSession, regime_id: uuid.UUID | None = None) -> int:
    """
    Applies an edited regime (regime_id: its companies) or an edited legal rate (None: every company) to the rates of
    the companies it concerns. Returns how many companies were resynced. No commit.
    """
    query = select(Company)
    if regime_id is not None:
        query = query.where(Company.fiscal_regime_id == regime_id)
    companies = (await db.execute(query)).scalars().all()
    regimes: dict = {}
    for company in companies:
        regime = None
        if company.fiscal_regime_id is not None:
            if company.fiscal_regime_id not in regimes:
                regimes[company.fiscal_regime_id] = (await db.execute(
                    select(FiscalRegime).where(FiscalRegime.id == company.fiscal_regime_id)
                )).scalar_one_or_none()
            regime = regimes[company.fiscal_regime_id]
        await sync_company_rates(db, company.id, regime)
    return len(companies)


async def regime_on(db: AsyncSession, company_id: uuid.UUID, day: date):
    """The fiscal regime in force for the company on that day (its history), or None before any regime."""
    row = (await db.execute(
        select(CompanyFiscalRegime)
        .where(CompanyFiscalRegime.company_id == company_id, CompanyFiscalRegime.valid_from <= day)
        .order_by(CompanyFiscalRegime.valid_from.desc(), CompanyFiscalRegime.created_at.desc())
        .limit(1)
    )).scalar_one_or_none()
    if row is None:
        return None
    return (await db.execute(select(FiscalRegime).where(FiscalRegime.id == row.fiscal_regime_id))).scalar_one_or_none()


async def list_regime_history(db: AsyncSession, company_id: uuid.UUID) -> list[dict]:
    """The company's regimes, most recent first, each with the day it took effect."""
    rows = (await db.execute(
        select(CompanyFiscalRegime, FiscalRegime.name)
        .join(FiscalRegime, FiscalRegime.id == CompanyFiscalRegime.fiscal_regime_id)
        .where(CompanyFiscalRegime.company_id == company_id)
        .order_by(CompanyFiscalRegime.valid_from.desc(), CompanyFiscalRegime.created_at.desc())
    )).all()
    return [{"regime": name, "valid_from": row.valid_from.isoformat()} for row, name in rows]
