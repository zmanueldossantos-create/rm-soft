"""
Pydantic schemas for a company's own self-service settings, editable by
its GESTOR - everything except the locked fiscal identity (name, NIF,
legal_person_type, fiscal_regime), which remains SUPER_ADMIN-only (see
decision on SUPER_ADMIN scope, section 2.4/4.1).
"""
import re
import uuid
from datetime import datetime

import phonenumbers
from pydantic import BaseModel, field_validator

EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")


def _validate_email(v: str) -> str:
    cleaned = v.strip()
    if not EMAIL_PATTERN.match(cleaned):
        raise ValueError("Email invalido - formato esperado: nome@dominio.com")
    return cleaned.lower()


def _validate_phone_required(v: str) -> str:
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
    return _validate_phone_required(v)


class CompanyContactUpdateRequest(BaseModel):
    """Self-service fields a GESTOR can update for their own company - not the locked fiscal identity."""
    email: str
    phone_number: str
    address: str | None = None

    short_name: str | None = None
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
    # Sale unit consistency checks ('off' / 'warn' / 'block'): only changed when sent.
    sale_unit_check_above_base: str | None = None
    sale_unit_check_below_cost: str | None = None
    sale_unit_check_same_factor: str | None = None
    issuance_mode: str = "MANUAL"
    electronic_signature_key: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return _validate_email(v)

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        return _validate_phone_required(v)

    @field_validator("phone_number_2")
    @classmethod
    def validate_phone_2(cls, v: str | None) -> str | None:
        return _validate_optional_phone(v)


class CompanyContactResponse(BaseModel):
    """Read-only view of a company's own info, including the locked fiscal identity."""
    id: uuid.UUID
    name: str
    nif: str
    email: str
    phone_number: str
    address: str | None
    logo_path: str | None
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
    sale_unit_check_above_base: str = "warn"
    sale_unit_check_below_cost: str = "warn"
    sale_unit_check_same_factor: str = "warn"
    issuance_mode: str
    electronic_signature_key: str | None

    class Config:
        from_attributes = True