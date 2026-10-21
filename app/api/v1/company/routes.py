"""
Self-service company contact info routes.
GESTOR can update their own company's address/phone/email (used on
invoices) - fiscal identity (name/NIF) stays SUPER_ADMIN-only, unchanged
here, per the decision on SUPER_ADMIN scope.
"""
import os
import uuid

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission
from app.models.user import User
from app.models.company import Company
from app.schemas.company_settings import CompanyContactUpdateRequest, CompanyContactResponse
from app.schemas.admin import BankAccountResponse
from app.services.company_service import list_bank_accounts, add_bank_account, update_bank_account, toggle_bank_account, BankAccountNotFoundError
from app.schemas.admin import BankAccountInput
from app.services.setup_checklist_service import get_setup_checklist
from app.services.support_service import list_support_sessions
from app.services.company_backup_jobs import (BackupSettingsError, backup_file, backup_view, get_backup_settings,
                                              list_backups, make_backup, save_backup_settings, settings_view)
from fastapi.responses import FileResponse
from pydantic import BaseModel

router = APIRouter(prefix="/api/v1/company", tags=["company"])


class BackupSettingsRequest(BaseModel):
    mode: str
    times: list[str] = []


def _duplicate_field_message(error: IntegrityError) -> str:
    detail = str(getattr(error, "orig", error))
    if "ix_companies_email" in detail:
        return "Já existe uma empresa registada com este email"
    if "ix_companies_phone_number" in detail:
        return "Já existe uma empresa registada com este número de telefone"
    return "Não foi possível guardar - dados já utilizados por outra empresa"


@router.get("/me/bank-accounts", response_model=list[BankAccountResponse])
async def get_my_company_bank_accounts(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company_bank_accounts:view")),
):
    """Read-only - GESTOR (and CAIXA, needed for the Caixa screen's FT payment block) see their own company's bank accounts; management stays SUPER_ADMIN-only."""
    return await list_bank_accounts(db, current_user.company_id)


@router.get("/me/setup")
async def get_my_company_setup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:manage")),
):
    """Configuração inicial: the set-up steps of the caller's company, each read from the real data."""
    return await get_setup_checklist(db, current_user.company_id)


@router.get("/me/backups")
async def get_my_company_backups(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:backup")),
):
    """Cópias de segurança: the settings (automatic / manual, the hours) and the copies kept."""
    settings = await get_backup_settings(db, current_user.company_id)
    return {"settings": settings_view(settings),
            "copies": [backup_view(r) for r in await list_backups(db, current_user.company_id)]}


@router.put("/me/backups/settings")
async def update_my_company_backup_settings(
    payload: BackupSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:backup")),
):
    """Automatic at 1 to 3 hours a day (Luanda), or manual only."""
    try:
        return settings_view(await save_backup_settings(db, current_user.company_id, payload.mode, payload.times))
    except BackupSettingsError as e:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e))


@router.post("/me/backups")
async def make_my_company_backup(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:backup")),
):
    """«Fazer cópia agora»."""
    return backup_view(await make_backup(db, current_user.company_id, "MANUAL", current_user.id))


@router.get("/me/backups/{backup_id}/download")
async def download_my_company_backup(
    backup_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:backup")),
):
    """A copy of this company only - never served by the web as a file address."""
    try:
        path, name = await backup_file(db, current_user.company_id, backup_id)
    except BackupSettingsError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    return FileResponse(path, media_type="application/zip", filename=name)


@router.get("/me/support-sessions")
async def get_my_company_support_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:manage")),
):
    """The RM SOFT support accesses to the company: who entered, when, why, until when."""
    return await list_support_sessions(db, current_user.company_id)


@router.get("/me", response_model=CompanyContactResponse)
async def get_my_company(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:view")),
):
    """Returns the caller's own company info."""
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    return result.scalar_one()


@router.patch("/me", response_model=CompanyContactResponse)
async def update_my_company_contact(
    payload: CompanyContactUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:manage")),
):
    """Updates the caller's own company contact info (address/phone/email only)."""
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one()

    # Pre-check uniqueness, excluding this company's own current row
    email_check = await db.execute(
        select(Company).where(Company.email == payload.email, Company.id != current_user.company_id)
    )
    if email_check.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma empresa registada com este email")

    phone_check = await db.execute(
        select(Company).where(Company.phone_number == payload.phone_number, Company.id != current_user.company_id)
    )
    if phone_check.scalar_one_or_none() is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Já existe uma empresa registada com este número de telefone")

    company.email = payload.email
    company.phone_number = payload.phone_number
    company.address = payload.address
    company.short_name = payload.short_name
    company.phone_number_2 = payload.phone_number_2
    company.website = payload.website
    company.city = payload.city
    company.province_id = payload.province_id
    company.municipality_id = payload.municipality_id
    company.primary_currency_id = payload.primary_currency_id
    company.secondary_currency_id = payload.secondary_currency_id
    company.uses_invoicing = payload.uses_invoicing
    company.auto_series_year = payload.auto_series_year if payload.uses_invoicing else False
    company.allows_future_sale_date = payload.allows_future_sale_date if payload.uses_invoicing else False
    # Sale unit checks: only what is sent changes - a screen that does not send them keeps the company's choice.
    for check in ("sale_unit_check_above_base", "sale_unit_check_below_cost", "sale_unit_check_same_factor"):
        value = getattr(payload, check)
        if value in ("off", "warn", "block"):
            setattr(company, check, value)
    company.suggests_last_document_date = payload.suggests_last_document_date if payload.uses_invoicing else False
    for option in ("stock_period_closing", "stock_check_at_period_end", "inventory_before_close"):  # stock controls: only changed when sent
        if getattr(payload, option) is not None:
            setattr(company, option, getattr(payload, option))
    if payload.expiry_alert_days is not None:  # lots: days of warning before an expiry date
        if not 1 <= payload.expiry_alert_days <= 365:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                                detail="O alerta de validade deve estar entre 1 e 365 dias")
        company.expiry_alert_days = payload.expiry_alert_days
    if payload.prescription_policy is not None:  # Farmácia: is the prescription's number required?
        from app.services.pharmacy_service import PRESCRIPTION_POLICIES
        if payload.prescription_policy not in PRESCRIPTION_POLICIES:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Regra de receita médica inválida")
        company.prescription_policy = payload.prescription_policy
    company.issuance_mode = payload.issuance_mode
    company.electronic_signature_key = payload.electronic_signature_key if payload.issuance_mode == "ELETRONICA" else None

    try:
        await db.commit()
    except IntegrityError as e:
        await db.rollback()
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=_duplicate_field_message(e))

    await db.refresh(company)
    return company


ALLOWED_LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
MAX_LOGO_SIZE_BYTES = 2 * 1024 * 1024  # 2MB


@router.post("/me/logo", response_model=CompanyContactResponse)
async def upload_my_company_logo(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:manage")),
):
    """Uploads/replaces the caller's own company logo. Stored locally (Phase 1)."""
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Formato de imagem inválido - use PNG, JPG ou WEBP")

    contents = await file.read()
    if len(contents) > MAX_LOGO_SIZE_BYTES:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Imagem demasiado grande - máximo 2MB")

    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one()

    # Remove any previous logo for this company (possibly a different
    # extension) so replacing the logo never leaves orphan files behind.
    for existing_ext in ALLOWED_LOGO_EXTENSIONS:
        old_path = os.path.join("uploads", "logos", f"{company.id}{existing_ext}")
        if os.path.exists(old_path):
            os.remove(old_path)

    # Filename is derived purely from company.id (a UUID) - the client's
    # original filename (which may contain accents, spaces or unsafe
    # characters) is never used for storage, only for extension detection.
    filename = f"{company.id}{ext}"
    filepath = os.path.join("uploads", "logos", filename)
    with open(filepath, "wb") as f:
        f.write(contents)

    company.logo_path = f"/uploads/logos/{filename}"
    await db.commit()
    await db.refresh(company)
    return company


@router.delete("/me/logo", response_model=CompanyContactResponse)
async def remove_my_company_logo(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company:manage")),
):
    """Removes the caller's own company logo."""
    result = await db.execute(select(Company).where(Company.id == current_user.company_id))
    company = result.scalar_one()

    for existing_ext in ALLOWED_LOGO_EXTENSIONS:
        old_path = os.path.join("uploads", "logos", f"{company.id}{existing_ext}")
        if os.path.exists(old_path):
            os.remove(old_path)

    company.logo_path = None
    await db.commit()
    await db.refresh(company)
    return company



@router.post("/me/bank-accounts", response_model=BankAccountResponse, status_code=status.HTTP_201_CREATED)
async def add_my_company_bank_account(
    payload: BankAccountInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company_bank_accounts:manage")),
):
    """GESTOR manages their own company's bank accounts directly - no SUPER_ADMIN needed for this."""
    return await add_bank_account(db, current_user.company_id, payload.bank_id, payload.account_number, payload.iban, payload.currency_id)


@router.patch("/me/bank-accounts/{account_id}", response_model=BankAccountResponse)
async def patch_my_company_bank_account(
    account_id: uuid.UUID,
    payload: BankAccountInput,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company_bank_accounts:manage")),
):
    try:
        return await update_bank_account(db, current_user.company_id, account_id, payload.bank_id, payload.account_number, payload.iban, payload.currency_id)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.patch("/me/bank-accounts/{account_id}/toggle-status", response_model=BankAccountResponse)
async def toggle_my_company_bank_account(
    account_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_permission("company_bank_accounts:manage")),
):
    try:
        return await toggle_bank_account(db, current_user.company_id, account_id)
    except BankAccountNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
