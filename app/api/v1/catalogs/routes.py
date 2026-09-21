"""
Routes for the 8 platform-wide base catalogs - all SUPER_ADMIN managed
(see discussion on the "Configuracoes" admin screen).
"""
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.api.deps import require_permission, require_role
from app.models.user import User
from app.schemas.catalog import (
    CountryRequest, CountryResponse,
    CurrencyRequest, CurrencyResponse,
    ProvinceRequest, ProvinceResponse,
    MunicipalityRequest, MunicipalityResponse,
    BankRequest, BankResponse,
    PaymentMethodCatalogRequest, PaymentMethodCatalogResponse,
    PaymentTermRequest, PaymentTermResponse,
    VatCodeRequest, VatCodeResponse,
    MovementTypeRequest, MovementTypeResponse,
    DocumentTypeRequest, DocumentTypeResponse,
    UnitOfMeasureCatalogRequest, UnitOfMeasureCatalogResponse,
    WithholdingTaxRequest, WithholdingTaxResponse,
    DenominationRequest, DenominationResponse,
)
from app.services import catalog_service
from app.services.catalog_service import CatalogItemNotFoundError

router = APIRouter(prefix="/api/v1/catalogs", tags=["catalogs"])


def _not_found(e: Exception):
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ---------- Country ----------

@router.get("/countries", response_model=list[CountryResponse])
async def get_countries(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_countries(db)


@router.post("/countries", response_model=CountryResponse, status_code=status.HTTP_201_CREATED)
async def post_country(payload: CountryRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_country(db, payload.code, payload.name)


@router.patch("/countries/{item_id}", response_model=CountryResponse)
async def patch_country(item_id: uuid.UUID, payload: CountryRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_country(db, item_id, payload.code, payload.name)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/countries/{item_id}/toggle-status", response_model=CountryResponse)
async def toggle_country(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_country(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- Currency ----------

@router.get("/currencies", response_model=list[CurrencyResponse])
async def get_currencies(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_currencies(db)


@router.post("/currencies", response_model=CurrencyResponse, status_code=status.HTTP_201_CREATED)
async def post_currency(payload: CurrencyRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_currency(db, payload.code, payload.name, payload.symbol)


@router.patch("/currencies/{item_id}", response_model=CurrencyResponse)
async def patch_currency(item_id: uuid.UUID, payload: CurrencyRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_currency(db, item_id, payload.code, payload.name, payload.symbol)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/currencies/{item_id}/toggle-status", response_model=CurrencyResponse)
async def toggle_currency(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_currency(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- Province ----------

@router.get("/provinces", response_model=list[ProvinceResponse])
async def get_provinces(country_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_provinces(db, country_id)


@router.post("/provinces", response_model=ProvinceResponse, status_code=status.HTTP_201_CREATED)
async def post_province(payload: ProvinceRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_province(db, payload.country_id, payload.name)


@router.patch("/provinces/{item_id}", response_model=ProvinceResponse)
async def patch_province(item_id: uuid.UUID, payload: ProvinceRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_province(db, item_id, payload.country_id, payload.name)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/provinces/{item_id}/toggle-status", response_model=ProvinceResponse)
async def toggle_province(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_province(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- Municipality ----------

@router.get("/municipalities", response_model=list[MunicipalityResponse])
async def get_municipalities(province_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_municipalities(db, province_id)


@router.post("/municipalities", response_model=MunicipalityResponse, status_code=status.HTTP_201_CREATED)
async def post_municipality(payload: MunicipalityRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_municipality(db, payload.province_id, payload.name)


@router.patch("/municipalities/{item_id}", response_model=MunicipalityResponse)
async def patch_municipality(item_id: uuid.UUID, payload: MunicipalityRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_municipality(db, item_id, payload.province_id, payload.name)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/municipalities/{item_id}/toggle-status", response_model=MunicipalityResponse)
async def toggle_municipality(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_municipality(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- Bank ----------

@router.get("/banks", response_model=list[BankResponse])
async def get_banks(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_banks(db)


@router.post("/banks", response_model=BankResponse, status_code=status.HTTP_201_CREATED)
async def post_bank(payload: BankRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_bank(db, payload.acronym, payload.full_name)


@router.patch("/banks/{item_id}", response_model=BankResponse)
async def patch_bank(item_id: uuid.UUID, payload: BankRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_bank(db, item_id, payload.acronym, payload.full_name)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/banks/{item_id}/toggle-status", response_model=BankResponse)
async def toggle_bank(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_bank(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- PaymentMethodCatalog ----------

@router.get("/payment-methods", response_model=list[PaymentMethodCatalogResponse])
async def get_payment_methods(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_billing", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_payment_methods(db)


@router.post("/payment-methods", response_model=PaymentMethodCatalogResponse, status_code=status.HTTP_201_CREATED)
async def post_payment_method(payload: PaymentMethodCatalogRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_payment_method(db, payload.code, payload.name, payload.allows_payment, payload.allows_receipt, payload.is_cash)


@router.patch("/payment-methods/{item_id}", response_model=PaymentMethodCatalogResponse)
async def patch_payment_method(item_id: uuid.UUID, payload: PaymentMethodCatalogRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_payment_method(db, item_id, payload.code, payload.name, payload.allows_payment, payload.allows_receipt, payload.is_cash)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/payment-methods/{item_id}/toggle-status", response_model=PaymentMethodCatalogResponse)
async def toggle_payment_method(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_payment_method(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- PaymentTerm ----------

@router.get("/payment-terms", response_model=list[PaymentTermResponse])
async def get_payment_terms(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_billing", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_payment_terms(db)


@router.post("/payment-terms", response_model=PaymentTermResponse, status_code=status.HTTP_201_CREATED)
async def post_payment_term(payload: PaymentTermRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_payment_term(db, payload.name, payload.fixed_days, payload.days, payload.months_fixed_day, payload.discount)


@router.patch("/payment-terms/{item_id}", response_model=PaymentTermResponse)
async def patch_payment_term(item_id: uuid.UUID, payload: PaymentTermRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_payment_term(db, item_id, payload.name, payload.fixed_days, payload.days, payload.months_fixed_day, payload.discount)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/payment-terms/{item_id}/toggle-status", response_model=PaymentTermResponse)
async def toggle_payment_term(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_payment_term(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- VatCode ----------

@router.get("/vat-codes", response_model=list[VatCodeResponse])
async def get_vat_codes(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_vat_codes(db)


@router.post("/vat-codes", response_model=VatCodeResponse, status_code=status.HTTP_201_CREATED)
async def post_vat_code(payload: VatCodeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_vat_code(
        db, payload.code, payload.name, payload.rate, payload.country_id,
        payload.valid_from, payload.valid_until, payload.observations,
    )


@router.patch("/vat-codes/{item_id}", response_model=VatCodeResponse)
async def patch_vat_code(item_id: uuid.UUID, payload: VatCodeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_vat_code(
            db, item_id, payload.code, payload.name, payload.rate, payload.country_id,
            payload.valid_from, payload.valid_until, payload.observations,
        )
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/vat-codes/{item_id}/toggle-status", response_model=VatCodeResponse)
async def toggle_vat_code(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_vat_code(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- DocumentType ----------

@router.get("/document-types", response_model=list[DocumentTypeResponse])
async def get_document_types(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_document_types(db)


@router.post("/document-types", response_model=DocumentTypeResponse, status_code=status.HTTP_201_CREATED)
async def post_document_type(payload: DocumentTypeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_document_type(db, payload.code, payload.name, payload.area, payload.electronic_eligible, payload.is_fiscal, payload.rules_dict())


@router.patch("/document-types/{item_id}", response_model=DocumentTypeResponse)
async def patch_document_type(item_id: uuid.UUID, payload: DocumentTypeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_document_type(db, item_id, payload.code, payload.name, payload.area, payload.electronic_eligible, payload.is_fiscal, payload.rules_dict())
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/document-types/{item_id}/toggle-status", response_model=DocumentTypeResponse)
async def toggle_document_type(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_document_type(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- MovementType ----------

@router.get("/movement-types", response_model=list[MovementTypeResponse])
async def get_movement_types(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_movement_types(db)


@router.post("/movement-types", response_model=MovementTypeResponse, status_code=status.HTTP_201_CREATED)
async def post_movement_type(payload: MovementTypeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_movement_type(db, payload.code, payload.name, payload.direction, payload.is_auto, payload.description)


@router.patch("/movement-types/{item_id}", response_model=MovementTypeResponse)
async def patch_movement_type(item_id: uuid.UUID, payload: MovementTypeRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_movement_type(db, item_id, payload.code, payload.name, payload.direction, payload.is_auto, payload.description)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/movement-types/{item_id}/toggle-status", response_model=MovementTypeResponse)
async def toggle_movement_type(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_movement_type(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- UnitOfMeasureCatalog ----------

@router.get("/units", response_model=list[UnitOfMeasureCatalogResponse])
async def get_units(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_reference", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_units(db)


@router.post("/units", response_model=UnitOfMeasureCatalogResponse, status_code=status.HTTP_201_CREATED)
async def post_unit(payload: UnitOfMeasureCatalogRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_unit(db, payload.code, payload.name)


@router.patch("/units/{item_id}", response_model=UnitOfMeasureCatalogResponse)
async def patch_unit(item_id: uuid.UUID, payload: UnitOfMeasureCatalogRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_unit(db, item_id, payload.code, payload.name)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/units/{item_id}/toggle-status", response_model=UnitOfMeasureCatalogResponse)
async def toggle_unit(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_unit(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)


# ---------- WithholdingTax ----------

@router.get("/withholding-taxes", response_model=list[WithholdingTaxResponse])
async def get_withholding_taxes(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_billing", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_withholding_taxes(db)


@router.post("/withholding-taxes", response_model=WithholdingTaxResponse, status_code=status.HTTP_201_CREATED)
async def post_withholding_tax(payload: WithholdingTaxRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    return await catalog_service.create_withholding_tax(db, payload.name, payload.rate, payload.tax_type)


@router.patch("/withholding-taxes/{item_id}", response_model=WithholdingTaxResponse)
async def patch_withholding_tax(item_id: uuid.UUID, payload: WithholdingTaxRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_withholding_tax(db, item_id, payload.name, payload.rate, payload.tax_type)
    except CatalogItemNotFoundError as e:
        _not_found(e)


@router.patch("/withholding-taxes/{item_id}/toggle-status", response_model=WithholdingTaxResponse)
async def toggle_withholding_tax(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_withholding_tax(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)

# ---------- Denomination ----------
@router.get("/denominations", response_model=list[DenominationResponse])
async def get_denominations_catalog(db: AsyncSession = Depends(get_db), current_user: User = Depends(require_permission("catalogs:view_billing", also_allow_roles=("SUPER_ADMIN",)))):
    return await catalog_service.list_denominations_catalog(db)
@router.post("/denominations", response_model=DenominationResponse, status_code=status.HTTP_201_CREATED)
async def post_denomination(payload: DenominationRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.create_denomination(db, payload.currency_id, payload.value, payload.denomination_type)
    except CatalogItemNotFoundError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
@router.patch("/denominations/{item_id}", response_model=DenominationResponse)
async def patch_denomination(item_id: uuid.UUID, payload: DenominationRequest, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.update_denomination(db, item_id, payload.currency_id, payload.value, payload.denomination_type)
    except CatalogItemNotFoundError as e:
        _not_found(e)
@router.patch("/denominations/{item_id}/toggle-status", response_model=DenominationResponse)
async def toggle_denomination(item_id: uuid.UUID, db: AsyncSession = Depends(get_db), current_user: User = Depends(require_role("SUPER_ADMIN"))):
    try:
        return await catalog_service.toggle_denomination(db, item_id)
    except CatalogItemNotFoundError as e:
        _not_found(e)
