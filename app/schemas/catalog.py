"""
Pydantic schemas for the 8 platform-wide base catalogs (see catalog_service.py).
"""
import uuid
from typing import Literal
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
    uses_bank_account: bool = False


class PaymentMethodCatalogResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    allows_payment: bool
    allows_receipt: bool
    is_cash: bool
    uses_bank_account: bool = False
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


class DocumentTypePreferenceResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    requires_payment_term: bool


class DocumentTypePreferenceUpdateRequest(BaseModel):
    requires_payment_term: bool


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
    description: str | None = None
    area: str | None = None
    electronic_eligible: bool = False
    is_fiscal: bool = True
    # Rules of the document (None = not sent, unchanged). The fiscal ones of an official type are locked server-side.
    saft_section: Literal["INVOICES", "PAYMENTS", "WORKING", "NONE"] | None = None
    revenue_sign: Literal[-1, 0, 1] | None = None
    requires_origin: bool | None = None
    has_lines: bool | None = None
    paid_on_issue: bool | None = None
    requires_payment_term: bool | None = None
    requires_customer: bool | None = None
    sent_to_agt: bool | None = None
    deducts_stock: bool | None = None
    accepts_credit_note: bool | None = None
    accepts_debit_note: bool | None = None
    accepts_receipt: bool | None = None
    convertible: bool | None = None
    issuable_in_invoices: bool | None = None
    issuable_at_pos: bool | None = None

    def rules_dict(self) -> dict:
        names = ("saft_section", "revenue_sign", "requires_origin", "has_lines", "paid_on_issue", "requires_payment_term", "requires_customer", "sent_to_agt", "deducts_stock",
                 "accepts_credit_note", "accepts_debit_note", "accepts_receipt", "convertible", "issuable_in_invoices", "issuable_at_pos")
        return {name: getattr(self, name) for name in names if getattr(self, name) is not None}


class DocumentTypeResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    area: str | None
    electronic_eligible: bool
    is_fiscal: bool
    is_active: bool
    rules_locked: bool = False
    saft_section: str = "NONE"
    revenue_sign: int = 0
    requires_origin: bool = False
    has_lines: bool = True
    paid_on_issue: bool = False
    requires_payment_term: bool = False
    requires_customer: bool = False
    sent_to_agt: bool = False
    deducts_stock: bool = False
    accepts_credit_note: bool = False
    accepts_debit_note: bool = False
    accepts_receipt: bool = False
    convertible: bool = False
    issuable_in_invoices: bool = False
    issuable_at_pos: bool = False

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
    # SAF-T WithholdingTaxType (the AGT e-invoicing API names the imposto predial "IP": converted at that boundary).
    tax_type: Literal["IRT", "II", "IS", "IVA", "IPU", "IAC", "OU"] | None = None


class WithholdingTaxResponse(BaseModel):
    id: uuid.UUID
    name: str
    rate: float
    is_active: bool
    tax_type: str | None = None

    class Config:
        from_attributes = True
