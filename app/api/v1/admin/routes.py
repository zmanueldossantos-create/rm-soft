"""
Platform-level administration routes.
Reserved for SUPER_ADMIN only - manages companies (tenants) and licenses,
never internal business operations of a specific company.
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_role
from app.models.company import Company
from app.models.user import User
from app.schemas.admin import CompanyCreateRequest, CompanyUpdateRequest, CompanyResponse
from app.schemas.platform_settings import PlatformSettingsResponse, PlatformSettingsUpdateRequest
from app.services.platform_settings_service import get_or_create_platform_settings, update_platform_settings
from app.schemas.fiscal_regime import FiscalRegimeCreateRequest, FiscalRegimeUpdateRequest, FiscalRegimeResponse
from app.services.fiscal_regime_service import (
    list_fiscal_regimes,
    create_fiscal_regime,
    update_fiscal_regime,
    toggle_fiscal_regime_status,
    FiscalRegimeNotFoundError,
)
from app.schemas.module import (
    ModuleCreateRequest, ModuleUpdateRequest, ModuleResponse,
    ModuleCapabilitiesRequest, ModuleCapabilitiesResponse, AdminOverviewResponse,
)
from app.services.module_service import (
    list_modules,
    create_module,
    update_module,
    toggle_module_status,
    ModuleNotFoundError,
)
from app.services.company_module_service import list_company_modules, set_company_modules
from app.services.sector_service import (
    build_overview, set_module_capabilities, reset_module_capabilities,
    UnknownCapabilityError, NoSectorDefaultsError,
)
from app.services.company_service import get_company_gestor
from app.schemas.auth import UserResponse
from app.services.company_service import (
    FiscalRegimeNotFoundError,
    create_company,
    update_company,
    delete_company,
    toggle_company_status,
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    InvalidCurrencySelectionError,
    list_bank_accounts,
    add_bank_account,
    update_bank_account,
    toggle_bank_account,
    BankAccountNotFoundError,
)
from app.schemas.admin import BankAccountInput, BankAccountResponse

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


@router.post("/companies", response_model=CompanyResponse, status_code=status.HTTP_201_CREATED)
async def create_new_company(
    payload: CompanyCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """
    Creates a new client company (tenant), its default VAT rates, its
    default warehouse, and its single GESTOR account - all together.
    """
    try:
        company = await create_company(
            db,
            name=payload.name,
            nif=payload.nif,
            email=payload.email,
            phone_number=payload.phone_number,
            gestor_full_name=payload.gestor_full_name,
            gestor_phone_number=payload.gestor_phone_number,
            gestor_password=payload.gestor_password,
            address=payload.address,
            commercial_registration_number=payload.commercial_registration_number,
            fiscal_regime_id=payload.fiscal_regime_id,
            module_ids=payload.module_ids,
            short_name=payload.short_name,
            legal_person_type=payload.legal_person_type,
            phone_number_2=payload.phone_number_2,
            website=payload.website,
            city=payload.city,
            province_id=payload.province_id,
            municipality_id=payload.municipality_id,
            primary_currency_id=payload.primary_currency_id,
            secondary_currency_id=payload.secondary_currency_id,
            uses_invoicing=payload.uses_invoicing,
            auto_series_year=payload.auto_series_year,
            allows_future_sale_date=payload.allows_future_sale_date,
            suggests_last_document_date=payload.suggests_last_document_date,
            issuance_mode=payload.issuance_mode,
            electronic_signature_key=payload.electronic_signature_key,
            bank_accounts=[b.model_dump() for b in payload.bank_accounts],
        )
    except CompanyAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidCurrencySelectionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return company


@router.get("/companies", response_model=list[CompanyResponse])
async def list_companies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Lists all client companies on the platform."""
    result = await db.execute(select(Company).order_by(Company.created_at.desc()))
    return result.scalars().all()


@router.patch("/companies/{company_id}", response_model=CompanyResponse)
async def edit_company(
    company_id: uuid.UUID,
    payload: CompanyUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Updates a company's editable fields (name, email, phone). NIF cannot be changed."""
    try:
        company = await update_company(
            db,
            company_id=company_id,
            name=payload.name,
            nif=payload.nif,
            email=payload.email,
            phone_number=payload.phone_number,
            address=payload.address,
            commercial_registration_number=payload.commercial_registration_number,
            short_name=payload.short_name,
            legal_person_type=payload.legal_person_type,
            phone_number_2=payload.phone_number_2,
            website=payload.website,
            city=payload.city,
            province_id=payload.province_id,
            municipality_id=payload.municipality_id,
            primary_currency_id=payload.primary_currency_id,
            secondary_currency_id=payload.secondary_currency_id,
            uses_invoicing=payload.uses_invoicing,
            auto_series_year=payload.auto_series_year,
            allows_future_sale_date=payload.allows_future_sale_date,
            suggests_last_document_date=payload.suggests_last_document_date,
            issuance_mode=payload.issuance_mode,
            electronic_signature_key=payload.electronic_signature_key,
            fiscal_regime_id=payload.fiscal_regime_id,
        )
    except CompanyAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except InvalidCurrencySelectionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except FiscalRegimeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return company


@router.delete("/companies/{company_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """
    Permanently deletes a company and its dependent data.
    Destructive - the frontend must ask for confirmation before calling this.
    """
    try:
        await delete_company(db, company_id)
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/companies/{company_id}/toggle-status", response_model=CompanyResponse)
async def toggle_status(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Activates or deactivates a client company."""
    try:
        company = await toggle_company_status(db, company_id)
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return company


@router.get("/settings", response_model=PlatformSettingsResponse)
async def get_platform_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """
    Returns the platform-wide software validation number (issued by AGT to
    RM SOFT itself, once homologated) - applies to every company's SAF-T
    export regardless of deployment mode (local or SaaS).
    """
    return await get_or_create_platform_settings(db)


@router.patch("/settings", response_model=PlatformSettingsResponse)
async def patch_platform_settings(
    payload: PlatformSettingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Updates the platform-wide SAF-T vendor identification fields."""
    return await update_platform_settings(
        db,
        software_validation_number=payload.software_validation_number,
        vendor_tax_id=payload.vendor_tax_id,
        product_id=payload.product_id,
        product_version=payload.product_version,
    )



@router.get("/fiscal-regimes", response_model=list[FiscalRegimeResponse])
async def get_fiscal_regimes(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Lists all fiscal regimes (Regime Geral, Exclusao, Simplificado, etc.)."""
    return await list_fiscal_regimes(db)


@router.post("/fiscal-regimes", response_model=FiscalRegimeResponse, status_code=status.HTTP_201_CREATED)
async def create_new_fiscal_regime(
    payload: FiscalRegimeCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Creates a new fiscal regime with its allowed VAT rates."""
    return await create_fiscal_regime(
        db, payload.name, payload.description, payload.allows_nor, payload.allows_red, payload.allows_ise,
        payload.allows_int, payload.allows_out,
        required_exemption_id=payload.required_exemption_id,
    )


@router.patch("/fiscal-regimes/{regime_id}", response_model=FiscalRegimeResponse)
async def edit_fiscal_regime(
    regime_id: uuid.UUID,
    payload: FiscalRegimeUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Updates a fiscal regime's name, description, and allowed VAT rates."""
    try:
        return await update_fiscal_regime(
            db, regime_id, payload.name, payload.description, payload.allows_nor, payload.allows_red, payload.allows_ise,
            payload.allows_int, payload.allows_out,
            required_exemption_id=payload.required_exemption_id,
        )
    except FiscalRegimeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/fiscal-regimes/{regime_id}/toggle-status", response_model=FiscalRegimeResponse)
async def toggle_fiscal_regime(
    regime_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Activates or deactivates a fiscal regime."""
    try:
        return await toggle_fiscal_regime_status(db, regime_id)
    except FiscalRegimeNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/modules", response_model=list[ModuleResponse])
async def get_modules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Lists all catalog modules (Hotel, Padaria, Bar, Restaurante, etc.)."""
    return await list_modules(db)


@router.post("/modules", response_model=ModuleResponse, status_code=status.HTTP_201_CREATED)
async def create_new_module(
    payload: ModuleCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Creates a new module type in the catalog."""
    return await create_module(db, payload.name, payload.description)


@router.patch("/modules/{module_id}", response_model=ModuleResponse)
async def edit_module(
    module_id: uuid.UUID,
    payload: ModuleUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Updates a module's name and description."""
    try:
        return await update_module(db, module_id, payload.name, payload.description)
    except ModuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/modules/{module_id}/toggle-status", response_model=ModuleResponse)
async def toggle_module(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Activates or deactivates a module in the catalog."""
    try:
        return await toggle_module_status(db, module_id)
    except ModuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/companies/{company_id}/modules", response_model=list[ModuleResponse])
async def get_company_modules(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Lists the modules currently granted to a company."""
    return await list_company_modules(db, company_id)


@router.put("/companies/{company_id}/modules", response_model=list[ModuleResponse])
async def put_company_modules(
    company_id: uuid.UUID,
    module_ids: list[uuid.UUID],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Replaces the company's granted modules with exactly this set."""
    await set_company_modules(db, company_id, module_ids)
    return await list_company_modules(db, company_id)


@router.get("/companies/{company_id}/gestor", response_model=UserResponse)
async def get_gestor_for_company(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Returns the company's single GESTOR user - used to target a password reset."""
    gestor = await get_company_gestor(db, company_id)
    if gestor is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gestor nao encontrado para esta empresa")
    return gestor


@router.get("/companies/{company_id}/bank-accounts", response_model=list[BankAccountResponse])
async def get_bank_accounts(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    return await list_bank_accounts(db, company_id)


@router.post("/companies/{company_id}/bank-accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def post_bank_account(
    company_id: uuid.UUID,
    payload: BankAccountInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    try:
        return await add_bank_account(db, company_id, payload.bank_id, payload.account_number, payload.iban, payload.currency_id)
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/companies/{company_id}/bank-accounts/{account_id}", response_model=BankAccountResponse)
async def patch_bank_account(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    payload: BankAccountInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    try:
        return await update_bank_account(db, account_id, payload.bank_id, payload.account_number, payload.iban, payload.currency_id)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/companies/{company_id}/bank-accounts/{account_id}/toggle-status", response_model=BankAccountResponse)
async def toggle_bank_account_status(
    company_id: uuid.UUID,
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    try:
        return await toggle_bank_account(db, account_id)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/overview", response_model=AdminOverviewResponse)
async def get_admin_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Global view: capabilities, modules (sectors), companies with what is active for each,
    and the impact list (capabilities switched off while the company already has data)."""
    return await build_overview(db)


@router.put("/modules/{module_id}/capabilities", response_model=ModuleCapabilitiesResponse)
async def put_module_capabilities(
    module_id: uuid.UUID,
    payload: ModuleCapabilitiesRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Sets which capabilities a module gives (dependencies are added automatically)."""
    try:
        codes = await set_module_capabilities(db, module_id, payload.capabilities)
    except ModuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except UnknownCapabilityError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return ModuleCapabilitiesResponse(module_id=module_id, capabilities=codes)


@router.post("/modules/{module_id}/capabilities/reset", response_model=ModuleCapabilitiesResponse)
async def post_reset_module_capabilities(
    module_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Back to the default capabilities of the module's sector."""
    try:
        codes = await reset_module_capabilities(db, module_id)
    except ModuleNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    except NoSectorDefaultsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return ModuleCapabilitiesResponse(module_id=module_id, capabilities=codes)


@router.get("/companies/{company_id}/regime-history")
async def get_company_regime_history(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """The company's fiscal regimes, most recent first, each with the day it took effect."""
    from app.services.company_service import list_regime_history
    return await list_regime_history(db, company_id)
