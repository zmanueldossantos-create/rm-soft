"""
Pydantic schemas for platform-level administration (SUPER_ADMIN only).
Extended (Video 1) with the 3-tab company fields observed in the
reference legalized software.
"""
import re
import uuid
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, field_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_nif(v: str) -> str:
    if not v.isdigit():
        raise ValueError("NIF invalido - deve conter apenas digitos")
    if len(v) < 9:
        raise ValueError("NIF invalido - deve ter pelo menos 9 digitos")
    return v


def _validate_phone(v: str) -> str:
    try:
        parsed = phonenumbers.parse(v, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Numero de telefone invalido")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


def _validate_optional_phone(v: str | None) -> str | None:
    if not v:
        return None
    return _validate_phone(v)


def _validate_name(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Nome da empresa nao pode estar vazio")
    return cleaned


def _validate_email(v: str) -> str:
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email invalido - formato esperado: nome@dominio.com")
    return cleaned.lower()


class BankAccountInput(BaseModel):
    bank_id: uuid.UUID
    account_number: str
    iban: str
    currency_id: uuid.UUID


class BankAccountResponse(BaseModel):
    id: uuid.UUID
    bank_id: uuid.UUID
    account_number: str
    iban: str
    currency_id: uuid.UUID
    is_active: bool

    class Config:
        from_attributes = True


class CompanyCreateRequest(BaseModel):
    name: str
    nif: str
    email: str
    phone_number: str
    address: str | None = None
    commercial_registration_number: str | None = None
    fiscal_regime_id: uuid.UUID | None = None
    module_ids: list[uuid.UUID] = []
    gestor_full_name: str
    gestor_phone_number: str
    gestor_password: str

    short_name: str | None = None
    legal_person_type: str = "JURIDICA"
    phone_number_2: str | None = None
    website: str | None = None
    city: str | None = None
    province_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    primary_currency_id: uuid.UUID | None = None
    secondary_currency_id: uuid.UUID | None = None
    uses_invoicing: bool = True
    auto_series_year: bool = True
    allows_future_sale_date: bool = False
    suggests_last_document_date: bool = False
    issuance_mode: str = "MANUAL"
    electronic_signature_key: str | None = None
    bank_accounts: list[BankAccountInput] = []

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("nif")
    @classmethod
    def validate_nif(cls, v: str) -> str:
        return _validate_nif(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("phone_number_2")
    @classmethod
    def validate_phone_2(cls, v: str | None) -> str | None:
        return _validate_optional_phone(v)

    @field_validator("gestor_full_name")
    @classmethod
    def validate_gestor_name(cls, v: str) -> str:
        cleaned = " ".join(v.split())
        if not cleaned:
            raise ValueError("Nome do gestor nao pode estar vazio")
        return cleaned

    @field_validator("gestor_phone_number")
    @classmethod
    def validate_gestor_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("gestor_password")
    @classmethod
    def validate_gestor_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Palavra-passe deve ter pelo menos 8 caracteres")
        return v


class CompanyUpdateRequest(BaseModel):
    name: str
    nif: str
    email: str
    phone_number: str
    address: str | None = None
    commercial_registration_number: str | None = None

    short_name: str | None = None
    legal_person_type: str = "JURIDICA"
    phone_number_2: str | None = None
    website: str | None = None
    city: str | None = None
    province_id: uuid.UUID | None = None
    municipality_id: uuid.UUID | None = None
    primary_currency_id: uuid.UUID | None = None
    secondary_currency_id: uuid.UUID | None = None
    uses_invoicing: bool = True
    auto_series_year: bool = True
    allows_future_sale_date: bool = False
    suggests_last_document_date: bool = False
    issuance_mode: str = "MANUAL"
    electronic_signature_key: str | None = None
    fiscal_regime_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("nif")
    @classmethod
    def validate_nif(cls, v: str) -> str:
        return _validate_nif(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone(v)

    @field_validator("phone_number_2")
    @classmethod
    def validate_phone_2(cls, v: str | None) -> str | None:
        return _validate_optional_phone(v)


class CompanyResponse(BaseModel):
    id: uuid.UUID
    name: str
    nif: str
    email: str
    phone_number: str
    address: str | None
    commercial_registration_number: str | None
    fiscal_regime_id: uuid.UUID | None
    is_active: bool
    created_at: datetime

    short_name: str | None
    legal_person_type: str
    phone_number_2: str | None
    website: str | None
    city: str | None
    province_id: uuid.UUID | None
    municipality_id: uuid.UUID | None
    primary_currency_id: uuid.UUID | None
    secondary_currency_id: uuid.UUID | None
    uses_invoicing: bool
    auto_series_year: bool
    allows_future_sale_date: bool
    suggests_last_document_date: bool
    issuance_mode: str
    electronic_signature_key: str | None

    class Config:
        from_attributes = True