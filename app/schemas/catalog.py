"""
Pydantic schemas for the 8 platform-wide base catalogs (see catalog_service.py).
"""
import uuid
from datetime import date

from pydantic import BaseModel


class CountryRequest(BaseModel):
    code: str
    name: str


class CountryResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool
    # Pre-fills the customer form (Dados Fiscais > Moeda) when a country is picked.
    default_currency_id: uuid.UUID | None = None

    class Config:
        from_attributes = True


class CurrencyRequest(BaseModel):
    code: str
    name: str
    symbol: str | None = None


class CurrencyResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    symbol: str | None
    is_active: bool

    class Config:
        from_attributes = True


class ProvinceRequest(BaseModel):
    country_id: uuid.UUID
    name: str


class ProvinceResponse(BaseModel):
    id: uuid.UUID
    country_id: uuid.UUID
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class MunicipalityRequest(BaseModel):
    province_id: uuid.UUID
    name: str


class MunicipalityResponse(BaseModel):
    id: uuid.UUID
    province_id: uuid.UUID
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class BankRequest(BaseModel):
    acronym: str
    full_name: str


class BankResponse(BaseModel):
    id: uuid.UUID
    acronym: str
    full_name: str
    is_active: bool

    class Config:
        from_attributes = True


class DenominationRequest(BaseModel):
    currency_id: uuid.UUID
    value: float
    denomination_type: str  # "NOTA" | "MOEDA"


class DenominationResponse(BaseModel):
    id: uuid.UUID
    currency_id: uuid.UUID
    value: float
    denomination_type: str
    is_active: bool

    class Config:
        from_attributes = True


class PaymentMethodCatalogRequest(BaseModel):
    code: str
    name: str
    allows_payment: bool = True
    allows_receipt: bool = True
    is_cash: bool = False


class PaymentMethodCatalogResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    allows_payment: bool
    allows_receipt: bool
    is_cash: bool
    is_active: bool

    class Config:
        from_attributes = True


class PaymentMethodPreferenceResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    allows_payment: bool
    allows_receipt: bool
    is_cash: bool
    available_at_pos: bool


class PaymentMethodPreferenceUpdateRequest(BaseModel):
    available_at_pos: bool


class PaymentTermRequest(BaseModel):
    name: str
    fixed_days: bool = False
    days: int = 0
    months_fixed_day: int = 0
    discount: float = 0


class PaymentTermResponse(BaseModel):
    id: uuid.UUID
    name: str
    fixed_days: bool
    days: int
    months_fixed_day: int
    discount: float
    is_active: bool

    class Config:
        from_attributes = True


class VatCodeRequest(BaseModel):
    code: str
    name: str
    rate: float
    country_id: uuid.UUID
    valid_from: date
    valid_until: date | None = None
    observations: str | None = None


class VatCodeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    rate: float
    country_id: uuid.UUID
    valid_from: date
    valid_until: date | None
    observations: str | None
    is_active: bool

    class Config:
        from_attributes = True


class DocumentTypeRequest(BaseModel):
    code: str
    name: str
    area: str | None = None
    electronic_eligible: bool = False
    is_fiscal: bool = True


class DocumentTypeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    area: str | None
    electronic_eligible: bool
    is_fiscal: bool
    is_active: bool

    class Config:
        from_attributes = True


class MovementTypeRequest(BaseModel):
    code: str
    name: str
    direction: str
    is_auto: bool = False
    description: str | None = None


class MovementTypeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    direction: str
    is_auto: bool
    description: str | None
    is_active: bool

    class Config:
        from_attributes = True


class UnitOfMeasureCatalogRequest(BaseModel):
    code: str
    name: str


class UnitOfMeasureCatalogResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    is_active: bool

    class Config:
        from_attributes = True


class WithholdingTaxRequest(BaseModel):
    name: str
    rate: float = 0


class WithholdingTaxResponse(BaseModel):
    id: uuid.UUID
    name: str
    rate: float
    is_active: bool

    class Config:
        from_attributes = True
