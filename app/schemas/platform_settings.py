"""
Pydantic schemas for platform-wide settings (SUPER_ADMIN only).
"""
import re
import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, field_validator


class PlatformSettingsResponse(BaseModel):
    id: uuid.UUID
    software_validation_number: str | None
    vendor_tax_id: str | None
    product_id: str | None
    product_version: str | None
    updated_at: datetime

    class Config:
        from_attributes = True


class PlatformSettingsUpdateRequest(BaseModel):
    software_validation_number: str | None = None
    vendor_tax_id: str | None = None
    product_id: str | None = None
    product_version: str | None = None


class SiteSettings(BaseModel):
    """The contacts the public site shows (rmsystem.co.ao): the WhatsApp button and the email."""
    site_whatsapp: str | None = None
    site_email: EmailStr | None = None

    class Config:
        from_attributes = True

    @field_validator("site_whatsapp", mode="before")
    @classmethod
    def _whatsapp(cls, value):
        value = (value or "").replace(" ", "").strip()
        if not value:
            return None
        if not re.fullmatch(r"\+\d{9,15}", value):
            raise ValueError("WhatsApp: número internacional, ex.: +244923000000")
        return value

    @field_validator("site_email", mode="before")
    @classmethod
    def _email(cls, value):
        return (value or "").strip() or None
