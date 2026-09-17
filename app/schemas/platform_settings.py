"""
Pydantic schemas for platform-wide settings (SUPER_ADMIN only).
"""
import uuid
from datetime import datetime

from pydantic import BaseModel


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
