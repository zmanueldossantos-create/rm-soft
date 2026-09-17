"""
Pydantic schemas for customers.
See specification v6/v7, section 4.1 (NIF required for AGT invoicing).
Extended (Video 2) with the 2-tab fields observed in the reference
legalized software.
"""
import re
import uuid
from datetime import date, datetime

import phonenumbers
from pydantic import BaseModel, field_validator, model_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_name(v: str) -> str:
    cleaned = " ".join(v.split())
    if not cleaned:
        raise ValueError("Nome do cliente nao pode estar vazio")
    return cleaned


def _validate_nif(v: str) -> str:
    cleaned = v.strip().upper()
    if not re.match(r"^[A-Z0-9]+$", cleaned):
        raise ValueError("NIF invalido - deve conter apenas letras e digitos")
    if len(cleaned) < 9:
        raise ValueError("NIF invalido - deve ter pelo menos 9 caracteres")
    return cleaned


def _validate_email(v: str | None) -> str | None:
    if not v:
        return None
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email invalido - formato esperado: nome@dominio.com")
    return cleaned.lower()


def _validate_phone_required(v: str) -> str:
    if not v:
        raise ValueError("Numero de telefone e obrigatorio")
    try:
        parsed = phonenumbers.parse(v, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Numero de telefone invalido")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


def _validate_phone(v: str | None) -> str | None:
    if not v:
        return None
    try:
        parsed = phonenumbers.parse(v, None)
        if not phonenumbers.is_valid_number(parsed):
            raise ValueError("Numero de telefone invalido")
        return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except phonenumbers.NumberParseException:
        raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


class CustomerCreateRequest(BaseModel):
    """Request to create a new customer. Only name and NIF are mandatory (section 4.1) - unless is_final_consumer, which forces the NIF to the SAF-T generic value server-side."""
    name: str
    nif: str = ""
    email: str | None = None
    phone_number: str
    address: str | None = None

    customer_code: str | None = None
    legal_person_type: str = "JURIDICA"
    is_final_consumer: bool = False
    description: str | None = None
    registration_date: date | None = None
    fiscal_name: str | None = None
    currency_id: uuid.UUID | None = None
    country_id: uuid.UUID | None = None
    province_id: uuid.UUID | None = None
    city: str | None = None
    payment_term_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    withholding_tax_id: uuid.UUID | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @model_validator(mode="after")
    def validate_nif_and_phone_unless_final_consumer(self):
        if not self.is_final_consumer:
            self.nif = _validate_nif(self.nif)
            self.phone_number = _validate_phone_required(self.phone_number)
        return self


class CustomerUpdateRequest(BaseModel):
    """Request to update a customer's editable fields."""
    name: str
    nif: str = ""
    email: str | None = None
    phone_number: str
    address: str | None = None

    customer_code: str | None = None
    legal_person_type: str = "JURIDICA"
    is_final_consumer: bool = False
    description: str | None = None
    registration_date: date | None = None
    fiscal_name: str | None = None
    currency_id: uuid.UUID | None = None
    country_id: uuid.UUID | None = None
    province_id: uuid.UUID | None = None
    city: str | None = None
    payment_term_id: uuid.UUID | None = None
    payment_method_id: uuid.UUID | None = None
    withholding_tax_id: uuid.UUID | None = None
    status: str = "ACTIVO"

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        return _validate_name(v)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str | None) -> str | None:
        return _validate_email(v)

    @model_validator(mode="after")
    def validate_nif_and_phone_unless_final_consumer(self):
        if not self.is_final_consumer:
            self.nif = _validate_nif(self.nif)
            self.phone_number = _validate_phone_required(self.phone_number)
        return self


class CustomerResponse(BaseModel):
    """Customer data returned to the client."""
    id: uuid.UUID
    name: str
    nif: str
    email: str | None
    phone_number: str | None
    address: str | None
    is_active: bool
    created_at: datetime

    customer_code: str | None
    legal_person_type: str
    is_final_consumer: bool
    description: str | None
    registration_date: date
    fiscal_name: str | None
    currency_id: uuid.UUID | None
    country_id: uuid.UUID | None
    province_id: uuid.UUID | None
    city: str | None
    payment_term_id: uuid.UUID | None
    payment_method_id: uuid.UUID | None
    withholding_tax_id: uuid.UUID | None
    status: str

    class Config:
        from_attributes = True


class CustomerBankLinkRequest(BaseModel):
    company_bank_account_id: uuid.UUID


class CustomerBankLinkResponse(BaseModel):
    id: uuid.UUID
    customer_id: uuid.UUID
    company_bank_account_id: uuid.UUID

    class Config:
        from_attributes = True


class CustomerCodeSuggestionResponse(BaseModel):
    suggested_code: str