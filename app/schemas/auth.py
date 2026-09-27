"""
Pydantic schemas for phone number authentication.
See specification v7, section 2.4.
"""
import phonenumbers
from pydantic import BaseModel, field_validator


class PhoneLoginRequest(BaseModel):
    """Login request: phone number + password."""
    phone_number: str
    password: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        """Validates and normalizes the number to E.164 format (ex. +244923456789)."""
        try:
            parsed = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Numero de telefone invalido")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


class TokenPair(BaseModel):
    """Token pair returned after a successful login."""
    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """Access token refresh request."""
    refresh_token: str


class UserCreateRequest(BaseModel):
    """User creation (by GESTOR only)."""
    full_name: str
    phone_number: str
    password: str
    role: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            parsed = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Numero de telefone invalido")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


class UserUpdateRequest(BaseModel):
    """User edit (by GESTOR only) - name, phone and role. Password changes go through the
    separate reset-password endpoint, kept deliberately apart from this one."""
    full_name: str
    phone_number: str
    role: str

    @field_validator("phone_number")
    @classmethod
    def validate_phone(cls, v: str) -> str:
        try:
            parsed = phonenumbers.parse(v, None)
            if not phonenumbers.is_valid_number(parsed):
                raise ValueError("Numero de telefone invalido")
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
        except phonenumbers.NumberParseException:
            raise ValueError("Formato de numero de telefone invalido (esperado: +244923456789)")


class UserResponse(BaseModel):
    """User data returned to the GESTOR managing their team."""
    id: str
    full_name: str
    phone_number: str
    role: str
    is_active: bool

    class Config:
        from_attributes = True

    @field_validator("id", mode="before")
    @classmethod
    def stringify_id(cls, v):
        return str(v)

    @field_validator("role", mode="before")
    @classmethod
    def stringify_role(cls, v):
        return v.value if hasattr(v, "value") else v


class PasswordResetRequest(BaseModel):
    """Admin-driven password reset (SUPER_ADMIN->GESTOR or GESTOR->team member)."""
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Palavra-passe deve ter pelo menos 8 caracteres")
        return v
