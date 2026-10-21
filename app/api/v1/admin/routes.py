"""
Platform-level administration routes.
Reserved for SUPER_ADMIN only - manages companies (tenants) and licenses,
never internal business operations of a specific company.
"""
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile, status
from pydantic import BaseModel
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
from app.services.company_backup_service import BackupError, export_company, inspect_backup, restore_company
from app.services.company_base_service import inspect_base
from app.services.company_backup_jobs import (BackupSettingsError, backup_file, backup_view, backups_overview,
                                              get_backup_settings, list_backups, make_backup, settings_view)
from fastapi.responses import FileResponse
from app.services.reference_catalog_service import (ReferenceCatalogError, catalog_meta, catalog_template,
                                                    delete_reference_product, import_catalog, list_reference_products,
                                                    product_view, save_reference_product)
from app.services.setup_checklist_service import get_setup_checklist
from app.services.support_service import SupportError, list_support_sessions, start_support
from app.schemas.auth import UserResponse
from app.services.company_service import (
    FiscalRegimeNotFoundError,
    create_company,
    update_company,
    delete_company,
    toggle_company_status,
    CompanyAlreadyExistsError,
    CompanyNotFoundError,
    get_company_or_raise,
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
            subdomain=payload.subdomain,
            base_token=payload.base_token,
            base_parts=payload.base_parts,
        )
    except BackupError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except CompanyAlreadyExistsError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
    except InvalidCurrencySelectionError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    return company


MAX_BACKUP_BYTES = 200 * 1024 * 1024  # a company's copy, images included


class ReferenceUnitInput(BaseModel):
    unit_of_measure_id: uuid.UUID | None = None
    factor: float | str | None = None
    barcode: str | None = None
    price: float | str | None = None


class ReferenceProductInput(BaseModel):
    barcode: str | None = None
    name: str = ""
    category: str | None = None
    unit_of_measure_id: uuid.UUID | None = None
    tax_category: str = ""
    exemption_id: uuid.UUID | None = None
    price: float | str | None = None
    sectors: list[str] = []
    is_active: bool = True
    units: list[ReferenceUnitInput] = []


@router.get("/reference-catalog/meta")
async def get_reference_catalog_meta(db: AsyncSession = Depends(get_db),
                                     current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """Catálogo de referência: the sectors with their counts, the units, the exemption motives."""
    return await catalog_meta(db)


@router.get("/reference-catalog")
async def get_reference_catalog(q: str = "", sector: str | None = None, limit: int = 100, offset: int = 0,
                                db: AsyncSession = Depends(get_db),
                                current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await list_reference_products(db, q, sector, min(max(limit, 1), 500), max(offset, 0))


@router.post("/reference-catalog")
async def create_reference_product(payload: ReferenceProductInput, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return product_view(await save_reference_product(db, payload.model_dump()))
    except ReferenceCatalogError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.put("/reference-catalog/{product_id}")
async def update_reference_product(product_id: uuid.UUID, payload: ReferenceProductInput,
                                   db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return product_view(await save_reference_product(db, payload.model_dump(), product_id))
    except ReferenceCatalogError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.delete("/reference-catalog/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_reference_product(product_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        await delete_reference_product(db, product_id)
    except ReferenceCatalogError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/reference-catalog-template")
async def get_reference_catalog_template(db: AsyncSession = Depends(get_db),
                                         current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """The Excel sheet to fill (with the codes to use)."""
    return Response(content=await catalog_template(db),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": 'attachment; filename="catalogo_referencia_modelo.xlsx"'})


@router.post("/reference-catalog-import")
async def import_reference_catalog(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                                   current_user: User = Depends(require_role("SUPER_ADMIN"))):
    """The filled sheet into the catalog: created, updated, and the rows refused with their reason."""
    try:
        return await import_catalog(db, await _backup_content(file))
    except ReferenceCatalogError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/backups")
async def get_backups_overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Cópias de segurança of every company: settings, last copy, failures, space used."""
    return await backups_overview(db)


@router.get("/companies/{company_id}/backups")
async def get_company_backups(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    return {"settings": settings_view(await get_backup_settings(db, company_id)),
            "copies": [backup_view(r) for r in await list_backups(db, company_id)]}


@router.post("/companies/{company_id}/backups")
async def make_company_backup(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """A copy now, made by the platform."""
    if await db.get(Company, company_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Empresa não encontrada")
    return backup_view(await make_backup(db, company_id, "PLATAFORMA", current_user.id))


@router.get("/backups/{backup_id}/download")
async def download_company_backup(
    backup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    try:
        path, name = await backup_file(db, None, backup_id)
    except BackupSettingsError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return FileResponse(path, media_type="application/zip", filename=name)


async def _backup_content(file: UploadFile) -> bytes:
    content = await file.read(MAX_BACKUP_BYTES + 1)
    if len(content) > MAX_BACKUP_BYTES:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Ficheiro demasiado grande (máx. 200 MB)")
    return content


@router.get("/companies/{company_id}/export")
async def export_company_backup(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """«Exportar»: the company's backup file - all its data and images, to keep or to restore later."""
    try:
        content, filename = await export_company(db, company_id)
    except BackupError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return Response(content=content, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.post("/company-base/inspect")
async def inspect_company_base(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """«Nova empresa» > Base: what a backup file can give a new company (its catalog) and the regime it takes; the
    file is kept an hour under the returned token, for the creation."""
    try:
        return await inspect_base(db, await _backup_content(file))
    except BackupError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/companies/restore/inspect")
async def inspect_company_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """«Restaurar», first step: what the file holds and what would stop it - nothing is written."""
    try:
        return await inspect_backup(db, await _backup_content(file))
    except BackupError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/companies/restore")
async def restore_company_backup(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """«Restaurar»: puts the company back from its file, identical - never over a company that exists here."""
    from sqlalchemy.exc import IntegrityError
    try:
        return await restore_company(db, await _backup_content(file))
    except BackupError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="Não foi possível restaurar: um dado do ficheiro já existe nesta plataforma ("
                                   + str(e.orig).split("DETAIL:")[-1].strip()[:200] + ")")


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
            subdomain=payload.subdomain,
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
        input_vat_deductible_pct=payload.input_vat_deductible_pct, turnover_vat_pct=payload.turnover_vat_pct, kept_exemption_ids=payload.kept_exemption_ids,
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
            input_vat_deductible_pct=payload.input_vat_deductible_pct, turnover_vat_pct=payload.turnover_vat_pct, kept_exemption_ids=payload.kept_exemption_ids,
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
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Gestor não encontrado para esta empresa")
    return gestor


class SupportStartRequest(BaseModel):
    reason: str


@router.post("/companies/{company_id}/support")
async def start_company_support(
    company_id: uuid.UUID,
    payload: SupportStartRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """«Entrar como suporte»: a one-time code opening the company's address with the gestor's screens, for an hour."""
    try:
        return await start_support(db, current_user, company_id, payload.reason)
    except SupportError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.get("/companies/{company_id}/support")
async def get_company_support_sessions(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """The support accesses to a company: who, when, why."""
    return await list_support_sessions(db, company_id)


@router.get("/companies/{company_id}/setup")
async def get_company_setup(
    company_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role("SUPER_ADMIN")),
):
    """Configuração inicial of a client company - lets the platform follow where each one stands."""
    try:
        await get_company_or_raise(db, company_id)
    except CompanyNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return await get_setup_checklist(db, company_id)


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
        return await update_bank_account(db, company_id, account_id, payload.bank_id, payload.account_number, payload.iban, payload.currency_id)
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
        return await toggle_bank_account(db, company_id, account_id)
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
