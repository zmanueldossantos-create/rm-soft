"""Schemas of the AI assistant's settings (platform and per company)."""
from pydantic import BaseModel, Field


class ProviderOption(BaseModel):
    value: str
    label: str


class PlatformAiResponse(BaseModel):
    provider: str | None
    model: str | None
    monthly_limit: int
    has_api_key: bool
    api_key_hint: str | None
    providers: list[ProviderOption]


class PlatformAiUpdateRequest(BaseModel):
    provider: str | None = None
    model: str | None = None
    api_key: str | None = None  # None = unchanged, "" = removed
    monthly_limit: int = Field(300, ge=0)


class AiTestResponse(BaseModel):
    answer: str
    seconds: float


class CompanyAiResponse(BaseModel):
    ai_enabled: bool
    whatsapp_enabled: bool
    telegram_enabled: bool
    email_enabled: bool
    monthly_limit: int | None
    effective_monthly_limit: int
    platform_monthly_limit: int
    confirm_documents: bool
    confirm_sends: bool
    platform_configured: bool


class CompanyAiSwitchesRequest(BaseModel):
    ai_enabled: bool = False
    whatsapp_enabled: bool = False
    telegram_enabled: bool = False
    email_enabled: bool = False
    monthly_limit: int | None = Field(None, ge=0)  # None = the platform's default


class CompanyAiConfirmationsRequest(BaseModel):
    confirm_documents: bool = True
    confirm_sends: bool = True
